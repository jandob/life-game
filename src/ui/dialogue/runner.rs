use bevy::prelude::*;
use bevy_yarnspinner::{events::DialogueCompleted, prelude::*};

use crate::{
    player::chat::{PlayerStartedChat, PlayerStoppedChat},
    story::{
        build_story_runner,
        phone::{note_command, note_done_command, phone_command},
        scripted::{await_walks_command, face_command, hide_command, show_command, walk_command},
        transition::{
            card_command, fade_in_command, fade_out_command, next_scene_command, place_command,
            start_queued_scene, ScreenFade,
        },
        StoryVars,
    },
    world::{
        ending::EndingTriggered,
        map::doors::{close_door_command, open_door_command},
    },
    GameState,
};

use super::{
    command::{end_demo_command, stop_chat_command},
    option_selection::{CreateOptions, OptionSelection},
    spawn::{DialogueBox, DialogueContent, DialogueRoot, OptionsBackground},
    typewriter::{Typewriter, WriteDialogueText},
};

#[derive(Component)]
pub struct RunnerFlags {
    pub active: bool,
    /// The start node, which also keys the runner.
    pub node: String,
    pub line: Option<LocalizedLine>,
    pub options: Option<OptionSelection>,
    /// Whether this conversation has presented a line yet. Until it has, its options are
    /// an action popup and the dialogue box stays hidden.
    pub presented_line: bool,
}

/// This is only fired when the dialogue runner isn't cached yet and was thus never spawned.
#[derive(Message)]
struct SpawnDialogueRunner {
    node: String,
}

impl RunnerFlags {
    fn new(node: String) -> Self {
        Self {
            active: true,
            node,
            line: None,
            options: None,
            presented_line: false,
        }
    }
}

/// Registers the custom Yarn commands on a runner.
fn add_story_commands(commands: &mut Commands, runner: &mut DialogueRunner) {
    let stop_chat = commands.register_system(stop_chat_command);
    let end_demo = commands.register_system(end_demo_command);
    let walk = commands.register_system(walk_command);
    let await_walks = commands.register_system(await_walks_command);
    let face = commands.register_system(face_command);
    let show = commands.register_system(show_command);
    let hide = commands.register_system(hide_command);
    let open_door = commands.register_system(open_door_command);
    let close_door = commands.register_system(close_door_command);
    let place = commands.register_system(place_command);
    let fade_out = commands.register_system(fade_out_command);
    let fade_in = commands.register_system(fade_in_command);
    let card = commands.register_system(card_command);
    let next_scene = commands.register_system(next_scene_command);
    let phone = commands.register_system(phone_command);
    let note = commands.register_system(note_command);
    let note_done = commands.register_system(note_done_command);
    runner
        .commands_mut()
        .add_command("stop_chat", stop_chat)
        .add_command("end_demo", end_demo)
        .add_command("walk", walk)
        .add_command("await_walks", await_walks)
        .add_command("face", face)
        .add_command("show", show)
        .add_command("hide", hide)
        .add_command("open_door", open_door)
        .add_command("close_door", close_door)
        .add_command("place", place)
        .add_command("fade_out", fade_out)
        .add_command("fade_in", fade_in)
        .add_command("card", card)
        .add_command("next_scene", next_scene)
        .add_command("phone", phone)
        .add_command("note", note)
        .add_command("note_done", note_done);
}

fn spawn_dialogue_runner(
    mut commands: Commands,
    mut typewriter: ResMut<Typewriter>,
    project: Res<YarnProject>,
    story_vars: Res<StoryVars>,
    mut fade: ResMut<ScreenFade>,
    mut ev_spawn_dialogue_runner: MessageReader<SpawnDialogueRunner>,
    mut ev_player_stopped_chat: MessageWriter<PlayerStoppedChat>,
) {
    for ev in ev_spawn_dialogue_runner.read() {
        typewriter.reset();
        let mut dialogue_runner = build_story_runner(&project, &mut commands, &story_vars);
        add_story_commands(&mut commands, &mut dialogue_runner);

        if let Err(err) = dialogue_runner.try_start_node(&ev.node) {
            error!("Cannot start dialogue node '{}': {err}", ev.node);
            // A scene that was queued behind a fade must not leave the screen black.
            fade.clear();
            ev_player_stopped_chat.write(PlayerStoppedChat);
            continue;
        }
        commands.spawn((dialogue_runner, RunnerFlags::new(ev.node.clone())));
    }
}

fn activate_dialogue_runner(
    mut commands: Commands,
    mut typewriter: ResMut<Typewriter>,
    mut q_runner_flags: Query<&mut RunnerFlags>,
    mut q_dialogue: Query<&mut Visibility, With<DialogueRoot>>,
    mut q_dialogue_content: Query<&mut Text, With<DialogueContent>>,
    mut ev_player_started_chat: MessageReader<PlayerStartedChat>,
    mut ev_create_options: MessageWriter<CreateOptions>,
    mut ev_write_dialogue_text: MessageWriter<WriteDialogueText>,
    mut ev_spawn_dialogue_runner: MessageWriter<SpawnDialogueRunner>,
) {
    let mut visibility = match q_dialogue.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    for ev in ev_player_started_chat.read() {
        *visibility = Visibility::Inherited;

        let mut cached = false;
        for mut flags in &mut q_runner_flags {
            if flags.node == ev.node {
                cached = true;
                flags.active = true;
                if let Some(option_selection) = &flags.options {
                    ev_create_options.write(CreateOptions(option_selection.clone()));
                    commands.insert_resource(option_selection.clone());
                }
                if let Some(line) = &flags.line {
                    typewriter.set_completed_line(line);
                    ev_write_dialogue_text.write(WriteDialogueText);
                }
            }
        }
        if !cached {
            if let Ok(mut dialogue_content) = q_dialogue_content.single_mut() {
                *dialogue_content = Text::default();
            }
            ev_spawn_dialogue_runner.write(SpawnDialogueRunner {
                node: ev.node.clone(),
            });
        }
    }
}

fn hide_dialogue(mut q_dialogue: Query<&mut Visibility, With<DialogueRoot>>) {
    let mut visibility = match q_dialogue.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };
    *visibility = Visibility::Hidden;
}

fn despawn_dialogue_runner(trigger: On<DialogueCompleted>, mut commands: Commands) {
    if let Ok(mut r) = commands.get_entity(trigger.entity) {
        r.despawn();
    }
}

fn hide_dialogue_on_completed(
    _trigger: On<DialogueCompleted>,
    mut q_dialogue: Query<&mut Visibility, With<DialogueRoot>>,
) {
    if let Ok(mut visibility) = q_dialogue.single_mut() {
        *visibility = Visibility::Hidden;
    }
}

fn deactivate_dialogue_runner(
    mut commands: Commands,
    mut q_runner_flags: Query<(Entity, &mut RunnerFlags)>,
) {
    for (entity, mut flags) in &mut q_runner_flags {
        // An action popup left with Escape is forgotten, so the next E starts the node
        // again and re-checks which actions are available.
        let popup = flags.options.as_ref().is_some_and(|options| options.popup);
        if flags.active && popup {
            commands.entity(entity).despawn();
            continue;
        }
        flags.active = false;
    }
}

/// Shows the dialogue box only once the active conversation has presented a line; an
/// action popup shows its options alone.
fn update_dialogue_box_visibility(
    q_runner_flags: Query<&RunnerFlags>,
    mut q_box: Query<&mut Visibility, With<DialogueBox>>,
    mut q_options: Query<&mut Node, With<OptionsBackground>>,
) {
    // Also hidden while a new runner is being spawned, so the box doesn't flash before
    // a popup.
    let popup = q_runner_flags
        .iter()
        .filter(|flags| flags.active)
        .all(|flags| !flags.presented_line);
    // A popup sits low in the middle, near the player; choices in a conversation stay
    // in the top right corner, clear of the dialogue box.
    for mut node in &mut q_options {
        let (top, bottom, left, right) = if popup {
            (Val::Auto, Val::Percent(20.0), Val::Percent(55.0), Val::Auto)
        } else {
            (Val::Px(10.0), Val::Auto, Val::Auto, Val::Px(10.0))
        };
        if node.top != top || node.bottom != bottom {
            node.top = top;
            node.bottom = bottom;
            node.left = left;
            node.right = right;
        }
    }
    for mut visibility in &mut q_box {
        let target = if popup {
            Visibility::Hidden
        } else {
            Visibility::Inherited
        };
        visibility.set_if_neq(target);
    }
}

fn monitor_active_runners(q_runner_flags: Query<&RunnerFlags>) {
    let mut active = 0;

    for flags in &q_runner_flags {
        if flags.active {
            active += 1;
        }
    }

    if active > 1 {
        error!("There are more than 1 active flags!");
    }
}

pub struct DialogueRunnerPlugin;

impl Plugin for DialogueRunnerPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<SpawnDialogueRunner>()
            .add_observer(despawn_dialogue_runner)
            .add_observer(hide_dialogue_on_completed)
            .add_systems(
                Update,
                (
                    start_queued_scene,
                    activate_dialogue_runner,
                    spawn_dialogue_runner,
                )
                    .chain()
                    .run_if(in_state(GameState::Gaming).and_then(resource_exists::<YarnProject>)),
            )
            .add_systems(
                Update,
                (
                    deactivate_dialogue_runner.run_if(on_message::<PlayerStoppedChat>),
                    monitor_active_runners,
                    update_dialogue_box_visibility,
                ),
            )
            .add_systems(
                Update,
                hide_dialogue
                    .run_if(on_message::<PlayerStoppedChat>.or_else(on_message::<EndingTriggered>)),
            );
    }
}
