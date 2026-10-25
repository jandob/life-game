//! Scripted movement for cutscene dialogue: actors, walks along Tiled paths,
//! facing and visibility. The Yarn commands in here are registered on every
//! dialogue runner by `ui::dialogue::runner`.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use bevy::prelude::*;
use bevy::time::Real;
use bevy_rapier2d::prelude::*;

use super::transition::ScreenFade;
use crate::npc::FourWayFacing;
use crate::player::Player;
use crate::world::map::tiled_map::TiledMap;
use crate::world::side_view::SideRooms;
use crate::GameState;

/// Walking speed of every scripted actor, in px/s.
pub const SCRIPT_WALK_SPEED: f32 = 210.0;
/// An actor this close to its target point has arrived.
const ARRIVE_DISTANCE: f32 = 6.0;
/// Seconds without progress after which an actor is placed at its target point.
const STUCK_SECONDS: f32 = 1.5;
/// Seconds an actor may take for one point on top of the time the walk itself needs,
/// whatever progress it makes. Bounds crawling that the progress check lets through.
const POINT_GRACE_SECONDS: f32 = 3.0;
/// A point may take this many times the free walking time before it is forced.
const POINT_SLOWDOWN: f32 = 3.0;
/// Progress (px) below which an actor counts as not moving.
const STUCK_PROGRESS: f32 = 6.0;
const NO_WAIT: &str = "no_wait";

/// Names an entity that dialogue commands can address, e.g. `Player` or `Samantha`.
#[derive(Component)]
pub struct Actor(pub String);

/// An active scripted walk along transform-space points.
#[derive(Component)]
pub struct ScriptedWalk {
    path: String,
    points: Vec<Vec2>,
    next: usize,
    done: Arc<AtomicBool>,
    best_dist: f32,
    stuck: Timer,
    /// Upper bound for the current point, set once its distance is known.
    deadline: Timer,
    /// Points after which the actor steps through a door (side view): on arriving at
    /// one, the actor is put at the next point at once.
    teleports: Vec<usize>,
}

impl ScriptedWalk {
    fn new(path: &str, points: Vec<Vec2>, done: Arc<AtomicBool>) -> Self {
        Self {
            path: path.to_string(),
            points,
            next: 0,
            done,
            best_dist: f32::MAX,
            stuck: Timer::from_seconds(STUCK_SECONDS, TimerMode::Once),
            deadline: Timer::from_seconds(STUCK_SECONDS, TimerMode::Once),
            teleports: Vec::new(),
        }
    }

    /// Releases anything waiting on this walk, e.g. when the actor is placed elsewhere.
    pub fn finish(&self) {
        self.done.store(true, Ordering::Relaxed);
    }

    /// Starts the clocks for a point that is `dist` px away.
    fn start_point(&mut self, dist: f32) {
        self.best_dist = dist;
        self.stuck.reset();
        let free_walk = dist / SCRIPT_WALK_SPEED;
        self.deadline = Timer::from_seconds(
            POINT_GRACE_SECONDS + POINT_SLOWDOWN * free_walk,
            TimerMode::Once,
        );
    }

    /// Ticks the fail-safes by `delta` and returns whether the actor has to be placed at
    /// its point: it made no progress for `STUCK_SECONDS`, or took far too long overall.
    fn is_stuck(&mut self, dist: f32, delta: Duration) -> bool {
        if !dist.is_finite() {
            return true;
        }
        if self.best_dist == f32::MAX {
            self.start_point(dist);
        } else if dist < self.best_dist - STUCK_PROGRESS {
            self.best_dist = dist;
            self.stuck.reset();
        } else {
            self.stuck.tick(delta);
        }
        self.deadline.tick(delta);
        self.stuck.is_finished() || self.deadline.is_finished()
    }
}

fn finished() -> Arc<AtomicBool> {
    Arc::new(AtomicBool::new(true))
}

/// `<<walk ACTOR PATH [no_wait]>>`
pub fn walk_command(
    In((actor, path, flag)): In<(String, String, Option<String>)>,
    mut commands: Commands,
    tiled_map: Res<TiledMap>,
    side_rooms: Option<Res<SideRooms>>,
    q_actors: Query<(Entity, &Actor, &Transform, Option<&ScriptedWalk>)>,
) -> Arc<AtomicBool> {
    let Some((entity, _, transform, old_walk)) = q_actors.iter().find(|(_, a, ..)| a.0 == actor)
    else {
        error!("walk: unknown actor '{actor}'");
        return finished();
    };
    let Some(points) = tiled_map.path(&path).filter(|p| !p.is_empty()) else {
        error!("walk: unknown or empty path '{path}'");
        return finished();
    };

    // A walk that gets replaced must not hold the dialogue forever.
    if let Some(old) = old_walk {
        old.done.store(true, Ordering::Relaxed);
    }

    let wait = match flag.as_deref() {
        None => true,
        Some(NO_WAIT) => false,
        Some(other) => {
            warn!("walk: unknown option '{other}', expected '{NO_WAIT}'; waiting");
            true
        }
    };
    let done = Arc::new(AtomicBool::new(false));
    let walk = match side_rooms {
        // Side-view rooms: a point in another room is reached through the doors between.
        Some(rooms) => {
            let route = rooms.route(transform.translation.truncate(), &points);
            let mut walk = ScriptedWalk::new(&path, route.points, done.clone());
            walk.teleports = route.teleports;
            walk
        }
        None => ScriptedWalk::new(&path, points, done.clone()),
    };
    commands.entity(entity).insert(walk);
    if wait {
        done
    } else {
        finished()
    }
}

/// `<<await_walks>>`: finished when no scripted walk is left.
pub fn await_walks_command(q_walks: Query<&ScriptedWalk>) -> Vec<Arc<AtomicBool>> {
    q_walks.iter().map(|w| w.done.clone()).collect()
}

fn direction_from_name(name: &str) -> Option<Vec2> {
    match name {
        "up" => Some(Vec2::Y),
        "down" => Some(Vec2::NEG_Y),
        "left" => Some(Vec2::NEG_X),
        "right" => Some(Vec2::X),
        _ => None,
    }
}

/// `<<face ACTOR DIR>>`, `DIR` being up, down, left, right or another actor.
pub fn face_command(
    In((actor, dir)): In<(String, String)>,
    q_actors: Query<(&Actor, &Transform)>,
    mut q_npcs: Query<(&Actor, &mut FourWayFacing), Without<Player>>,
    mut q_player: Query<(&Actor, &mut Player)>,
) {
    let Some(self_pos) = q_actors
        .iter()
        .find(|(a, _)| a.0 == actor)
        .map(|(_, t)| t.translation.truncate())
    else {
        error!("face: unknown actor '{actor}'");
        return;
    };
    let direction = match direction_from_name(&dir) {
        Some(d) => d,
        None => match q_actors.iter().find(|(a, _)| a.0 == dir) {
            Some((_, t)) => t.translation.truncate() - self_pos,
            None => {
                error!("face: '{dir}' is neither a direction nor an actor");
                return;
            }
        },
    };

    for (a, mut facing) in &mut q_npcs {
        if a.0 == actor {
            facing.facing = direction;
        }
    }
    for (a, mut player) in &mut q_player {
        if a.0 == actor {
            player.current_direction = direction;
        }
    }
}

fn set_visible(
    commands: &mut Commands,
    actor: &str,
    visible: bool,
    q_actors: &Query<(Entity, &Actor, Option<&Children>)>,
    q_colliders: &Query<(), With<Collider>>,
) {
    let Some((entity, _, children)) = q_actors.iter().find(|(_, a, _)| a.0 == actor) else {
        error!("show/hide: unknown actor '{actor}'");
        return;
    };
    commands.entity(entity).insert(if visible {
        Visibility::Inherited
    } else {
        Visibility::Hidden
    });
    for child in children.into_iter().flatten() {
        if q_colliders.contains(*child) {
            if visible {
                commands.entity(*child).remove::<ColliderDisabled>();
            } else {
                commands.entity(*child).insert(ColliderDisabled);
            }
        }
    }
}

/// `<<show ACTOR>>`
pub fn show_command(
    In(actor): In<String>,
    mut commands: Commands,
    q_actors: Query<(Entity, &Actor, Option<&Children>)>,
    q_colliders: Query<(), With<Collider>>,
) {
    set_visible(&mut commands, &actor, true, &q_actors, &q_colliders);
}

/// `<<hide ACTOR>>`
pub fn hide_command(
    In(actor): In<String>,
    mut commands: Commands,
    q_actors: Query<(Entity, &Actor, Option<&Children>)>,
    q_colliders: Query<(), With<Collider>>,
) {
    set_visible(&mut commands, &actor, false, &q_actors, &q_colliders);
}

/// Moves every actor with a `ScriptedWalk`. Kinematic actors step their transform,
/// dynamic ones (the player) get a velocity so that colliders still apply.
///
/// The fail-safes run on real time, so they fire even when virtual time stands still.
pub(crate) fn scripted_walk(
    mut commands: Commands,
    time: Res<Time>,
    real_time: Res<Time<Real>>,
    mut q_walkers: Query<(
        Entity,
        Option<&Actor>,
        &mut ScriptedWalk,
        &mut Transform,
        Option<&mut Velocity>,
        Option<&mut FourWayFacing>,
        Option<&mut Player>,
    )>,
    mut fade: Option<ResMut<ScreenFade>>,
) {
    let dt = time.delta_secs();

    for (entity, actor, mut walk, mut transform, mut velocity, mut facing, mut player) in
        &mut q_walkers
    {
        let pos = transform.translation.truncate();
        let target = walk.points[walk.next];
        let to_target = target - pos;
        let dist = to_target.length();

        let mut arrived = dist <= ARRIVE_DISTANCE;
        if !arrived && walk.is_stuck(dist, real_time.delta()) {
            warn!(
                "Scripted walk of '{}' on path '{}' is stuck {dist:.0}px from point {} {target:?} (actor at {pos:?}), placing the actor there",
                actor.map_or("?", |a| a.0.as_str()),
                walk.path,
                walk.next,
            );
            arrived = true;
        }

        if arrived {
            transform.translation.x = target.x;
            transform.translation.y = target.y;
            if walk.teleports.contains(&walk.next) && walk.next + 1 < walk.points.len() {
                walk.next += 1;
                let through = walk.points[walk.next];
                transform.translation.x = through.x;
                transform.translation.y = through.y;
                if let (Some(_), Some(fade)) = (player.as_ref(), fade.as_mut()) {
                    fade.dip();
                }
            }
            walk.next += 1;
            walk.best_dist = f32::MAX;
            walk.stuck.reset();
            if walk.next >= walk.points.len() {
                if let Some(velocity) = velocity.as_mut() {
                    velocity.linear = Vec2::ZERO;
                }
                walk.done.store(true, Ordering::Relaxed);
                commands.entity(entity).remove::<ScriptedWalk>();
            }
            continue;
        }

        let dir = to_target / dist;
        if let Some(facing) = facing.as_mut() {
            facing.facing = dir;
        }
        if let Some(player) = player.as_mut() {
            player.current_direction = dir;
        }
        if dt <= 0.0 {
            continue;
        }
        match velocity.as_mut() {
            Some(velocity) => velocity.linear = dir * SCRIPT_WALK_SPEED.min(dist / dt),
            None => {
                let step = (SCRIPT_WALK_SPEED * dt).min(dist);
                transform.translation += (dir * step).extend(0.0);
            }
        }
    }
}

pub struct ScriptedPlugin;

impl Plugin for ScriptedPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, scripted_walk.run_if(in_state(GameState::Gaming)));
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use bevy::time::TimeUpdateStrategy;
    use bevy_yarnspinner::TaskFinishedIndicator;

    use super::*;
    use crate::world::map::tiled_map::{ObjectLayerData, TiledObject};

    fn path_object(name: &str, points: &[Vec2]) -> TiledObject {
        TiledObject {
            name: name.to_string(),
            obj_type: String::new(),
            x: points[0].x,
            y: points[0].y,
            width: 0.0,
            height: 0.0,
            properties: Default::default(),
            points: points.to_vec(),
        }
    }

    fn test_app() -> App {
        test_app_with(false)
    }

    /// With `physics`, frames last 16 ms: rapier steps at most 1/60 s per frame.
    fn test_app_with(physics: bool) -> App {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        if physics {
            app.add_plugins((
                TransformPlugin,
                AssetPlugin::default(),
                RapierPhysicsPlugin::<NoUserData>::default(),
            ));
            app.init_asset::<Mesh>();
        }
        let frame = Duration::from_millis(if physics { 16 } else { 50 });
        app.insert_resource(TimeUpdateStrategy::ManualDuration(frame))
            .insert_resource(TiledMap {
                tile_size: 48.0,
                width: 40,
                height: 40,
                layers: Vec::new(),
                tilesets: Vec::new(),
                image_layers: Vec::new(),
                side_view: false,
                object_layers: vec![ObjectLayerData {
                    name: "Paths".to_string(),
                    objects: vec![
                        path_object("There", &[Vec2::new(100.0, 100.0), Vec2::new(160.0, 100.0)]),
                        path_object("Single", &[Vec2::new(100.0, 100.0)]),
                    ],
                }],
            })
            .add_systems(Update, scripted_walk);
        app.world_mut().spawn((
            Actor("Walker".to_string()),
            FourWayFacing {
                facing: Vec2::NEG_Y,
            },
            Transform::from_xyz(0.0, 0.0, 0.0),
        ));
        app.update();
        app
    }

    #[test]
    fn blocking_walk_finishes_at_the_last_point() {
        let mut app = test_app();
        let walk = app.world_mut().register_system(walk_command);
        let done = app
            .world_mut()
            .run_system_with(walk, ("Walker".to_string(), "There".to_string(), None))
            .unwrap();
        assert!(!done.is_finished());

        let end = app.world().resource::<TiledMap>().path("There").unwrap()[1];
        for _ in 0..400 {
            if done.is_finished() {
                break;
            }
            app.update();
        }
        assert!(done.is_finished(), "the walk never finished");

        let mut q = app.world_mut().query::<(&Transform, &FourWayFacing)>();
        let (transform, facing) = q.single(app.world()).unwrap();
        assert!(transform.translation.truncate().distance(end) < 0.01);
        assert!(
            facing.facing.x > 0.0,
            "faces the direction of the last segment"
        );
        let mut walks = app.world_mut().query::<&ScriptedWalk>();
        assert_eq!(walks.iter(app.world()).count(), 0);
    }

    #[test]
    fn face_show_and_hide_commands() {
        let mut app = test_app();
        let walker = {
            let mut q = app.world_mut().query_filtered::<Entity, With<Actor>>();
            q.single(app.world()).unwrap()
        };
        let collider = app.world_mut().spawn(Collider::ball(16.0)).id();
        app.world_mut().entity_mut(walker).add_child(collider);
        app.world_mut().spawn((
            Actor("Other".to_string()),
            Player::default(),
            Transform::from_xyz(50.0, 0.0, 0.0),
        ));

        let face = app.world_mut().register_system(face_command);
        let run_face = |app: &mut App, actor: &str, dir: &str| {
            app.world_mut()
                .run_system_with(face, (actor.to_string(), dir.to_string()))
                .unwrap()
        };
        run_face(&mut app, "Walker", "up");
        assert_eq!(
            app.world().get::<FourWayFacing>(walker).unwrap().facing,
            Vec2::Y
        );
        run_face(&mut app, "Walker", "Other");
        assert!(app.world().get::<FourWayFacing>(walker).unwrap().facing.x > 0.0);
        run_face(&mut app, "Other", "left");
        let mut q = app.world_mut().query::<&Player>();
        assert_eq!(
            q.single(app.world()).unwrap().current_direction,
            Vec2::NEG_X
        );
        // Unknown names only log
        run_face(&mut app, "Nobody", "up");
        run_face(&mut app, "Walker", "sideways");

        let hide = app.world_mut().register_system(hide_command);
        let show = app.world_mut().register_system(show_command);
        app.world_mut()
            .run_system_with(hide, "Walker".to_string())
            .unwrap();
        assert_eq!(
            app.world().get::<Visibility>(walker),
            Some(&Visibility::Hidden)
        );
        assert!(app.world().get::<ColliderDisabled>(collider).is_some());
        app.world_mut()
            .run_system_with(show, "Walker".to_string())
            .unwrap();
        assert_eq!(
            app.world().get::<Visibility>(walker),
            Some(&Visibility::Inherited)
        );
        assert!(app.world().get::<ColliderDisabled>(collider).is_none());
    }

    #[test]
    fn no_wait_and_unknown_names_finish_immediately() {
        let mut app = test_app();
        let walk = app.world_mut().register_system(walk_command);

        let no_wait = app
            .world_mut()
            .run_system_with(
                walk,
                (
                    "Walker".to_string(),
                    "There".to_string(),
                    Some("no_wait".to_string()),
                ),
            )
            .unwrap();
        assert!(no_wait.is_finished());

        let await_walks = app.world_mut().register_system(await_walks_command);
        let pending = app.world_mut().run_system(await_walks).unwrap();
        assert!(
            !pending.is_finished(),
            "await_walks waits for the running walk"
        );

        let unknown_actor = app
            .world_mut()
            .run_system_with(walk, ("Nobody".to_string(), "There".to_string(), None))
            .unwrap();
        assert!(unknown_actor.is_finished());
        let unknown_path = app
            .world_mut()
            .run_system_with(walk, ("Walker".to_string(), "Nowhere".to_string(), None))
            .unwrap();
        assert!(unknown_path.is_finished());
    }

    /// A player like the real one: dynamic body, 96x192 sheet, feet collider.
    fn spawn_player(app: &mut App, pos: Vec2) -> Entity {
        let (collider, local) = crate::character::REALISTIC.feet_collider();
        let feet = app.world_mut().spawn((collider, local)).id();
        app.world_mut()
            .spawn((
                Actor("Player".to_string()),
                Player::default(),
                RigidBody::Dynamic,
                LockedAxes::ROTATION_LOCKED,
                Velocity::zero(),
                Ccd::enabled(),
                crate::character::REALISTIC.transform(pos),
            ))
            .add_child(feet)
            .id()
    }

    fn start_walk(app: &mut App, actor: &str, path: &str) -> Arc<AtomicBool> {
        let walk = app.world_mut().register_system(walk_command);
        app.world_mut()
            .run_system_with(walk, (actor.to_string(), path.to_string(), None))
            .unwrap()
    }

    /// Updates until the walk is done and returns the seconds it took.
    fn run_until_done(app: &mut App, done: &AtomicBool, max_seconds: f32) -> f32 {
        let start = app.world().resource::<Time<Real>>().elapsed_secs();
        loop {
            app.update();
            let elapsed = app.world().resource::<Time<Real>>().elapsed_secs() - start;
            if done.load(Ordering::Relaxed) || elapsed > max_seconds {
                return elapsed;
            }
        }
    }

    fn position(app: &App, entity: Entity) -> Vec2 {
        app.world()
            .get::<Transform>(entity)
            .unwrap()
            .translation
            .truncate()
    }

    #[test]
    fn dynamic_player_walks_at_full_speed_to_its_points() {
        let mut app = test_app_with(true);
        let points = app.world().resource::<TiledMap>().path("Single").unwrap();
        let start = points[0] - Vec2::new(300.0, 0.0);
        let player = spawn_player(&mut app, start);
        app.update();

        let done = start_walk(&mut app, "Player", "Single");
        for _ in 0..60 {
            app.update();
        }
        // About a second in (60 frames of 16 ms), at 210 px/s
        let travelled = position(&app, player).x - start.x;
        assert!(
            (150.0..=230.0).contains(&travelled),
            "player travelled {travelled}px in a second, expected about {SCRIPT_WALK_SPEED}"
        );
        assert!(!done.load(Ordering::Relaxed));

        let seconds = run_until_done(&mut app, &done, 3.0);
        assert!(done.load(Ordering::Relaxed), "the walk never finished");
        assert!(seconds < 1.5, "took {seconds}s more");
        assert!(position(&app, player).distance(points[0]) < 0.01);
    }

    #[test]
    fn blocked_walk_places_the_actor_within_the_stuck_time() {
        let mut app = test_app_with(true);
        let points = app.world().resource::<TiledMap>().path("Single").unwrap();
        let start = points[0] - Vec2::new(300.0, 0.0);
        let player = spawn_player(&mut app, start);
        // A wall between the player and the first point
        app.world_mut().spawn((
            RigidBody::Fixed,
            Collider::cuboid(10.0, 400.0),
            Transform::from_translation((start + Vec2::new(150.0, 0.0)).extend(0.0)),
        ));
        app.update();

        let done = start_walk(&mut app, "Player", "Single");
        // 100 px to the wall at 210 px/s, then the stuck time
        let seconds = run_until_done(&mut app, &done, 5.0);
        assert!(done.load(Ordering::Relaxed), "the walk never finished");
        assert!(seconds < 0.5 + STUCK_SECONDS + 0.5, "took {seconds}s");
        assert!(position(&app, player).distance(points[0]) < 0.01);
    }

    #[test]
    fn fail_safe_does_not_depend_on_virtual_time() {
        let mut app = test_app();
        app.world_mut().resource_mut::<Time<Virtual>>().pause();
        let done = start_walk(&mut app, "Walker", "Single");
        let seconds = run_until_done(&mut app, &done, 5.0);
        assert!(done.load(Ordering::Relaxed), "the walk never finished");
        assert!(seconds < STUCK_SECONDS + 0.2, "took {seconds}s");
    }

    #[test]
    fn crawling_actor_is_forced_after_the_point_deadline() {
        let mut walk = ScriptedWalk::new(
            "There",
            vec![Vec2::new(1000.0, 0.0)],
            Arc::new(AtomicBool::new(false)),
        );
        let frame = Duration::from_millis(100);
        let mut dist = 1000.0;
        let mut seconds = 0.0;
        // 8 px/s: more progress than STUCK_PROGRESS per stuck time, but far too slow
        while !walk.is_stuck(dist, frame) {
            dist -= 0.8;
            seconds += 0.1;
            assert!(seconds < 30.0, "never forced");
        }
        let limit = POINT_GRACE_SECONDS + POINT_SLOWDOWN * 1000.0 / SCRIPT_WALK_SPEED;
        assert!(
            (seconds - limit).abs() < 0.3,
            "forced after {seconds}s, limit {limit}s"
        );
    }

    #[test]
    fn nan_distance_is_stuck_at_once() {
        let mut walk =
            ScriptedWalk::new("There", vec![Vec2::ZERO], Arc::new(AtomicBool::new(false)));
        assert!(walk.is_stuck(f32::NAN, Duration::from_millis(16)));
    }
}
