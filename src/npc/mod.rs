mod spawn;
mod wander;

use strum_macros::{Display, EnumString};

use bevy::prelude::*;
use bevy_rapier2d::plugin::PhysicsSet;

use crate::animation::{character_clip, play_character_clip, CharacterAnim, SpriteAnimator};
use crate::story::scripted::ScriptedWalk;
use crate::GameState;

/// Character ids. Used for the Tiled `NPCs` object names, the speaker table
/// and as target of the ending sequence.
#[derive(Clone, Copy, Debug, Display, PartialEq, EnumString)]
pub enum NpcDialogue {
    Samantha,
}

pub struct NpcPlugin;

impl Plugin for NpcPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((spawn::NpcSpawnPlugin, wander::WanderPlugin))
            .add_systems(
                PostUpdate,
                animate_actors
                    .before(PhysicsSet::Writeback)
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}

#[derive(Component)]
pub struct Npc {
    /// Which character this is.
    pub id: NpcDialogue,
}

/// The direction a four-direction character sheet NPC faces while it stands still.
/// Changed only by scripted `walk` and `face` commands.
#[derive(Component)]
pub struct FourWayFacing {
    pub facing: Vec2,
}

/// Walk while a scripted walk is active, else idle in the facing direction.
fn animate_actors(
    mut q_npcs: Query<
        (
            &FourWayFacing,
            Option<&ScriptedWalk>,
            &mut SpriteAnimator,
            &mut Sprite,
        ),
        With<Npc>,
    >,
) {
    for (facing, walk, mut animator, mut sprite) in &mut q_npcs {
        let anim = if walk.is_some() {
            CharacterAnim::Walk
        } else {
            CharacterAnim::Idle
        };
        play_character_clip(&mut animator, &mut sprite, character_clip(facing.facing, anim));
    }
}
