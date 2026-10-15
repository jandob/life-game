use bevy::prelude::*;
use bevy_yarnspinner::{events::DialogueCompleted, prelude::*};

use crate::{
    player::chat::{PlayerStartedChat, PlayerStoppedChat},
    story::{
        build_story_runner,
        scripted::{await_walks_command, face_command, hide_command, show_command, walk_command},
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
    spawn::{DialogueContent, DialogueRoot},
    typewriter::{Typewriter, WriteDialogueText},
};

#[derive(Component)]
pub struct RunnerFlags {
    pub active: bool,
    /// The start node, which also keys the runner.
    pub node: String,
    pub line: Option<LocalizedLine>,
    pub options: Option<OptionSelection>,
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
        .add_command("close_door", close_door);
}

fn spawn_dialogue_runner(
    mut commands: Commands,
    mut typewriter: ResMut<Typewriter>,
    project: Res<YarnProject>,
    story_vars: Res<StoryVars>,
    mut ev_spawn_dialogue_runner: MessageReader<SpawnDialogueRunner>,
    mut ev_player_stopped_chat: MessageWriter<PlayerStoppedChat>,
) {
    for ev in ev_spawn_dialogue_runner.read() {
        typewriter.reset();
        let mut dialogue_runner = build_story_runner(&project, &mut commands, &story_vars);
        add_story_commands(&mut commands, &mut dialogue_runner);

        if let Err(err) = dialogue_runner.try_start_node(&ev.node) {
            error!("Cannot start dialogue node '{}': {err}", ev.node);
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

fn deactivate_dialogue_runner(mut q_runner_flags: Query<&mut RunnerFlags>) {
    for mut flags in &mut q_runner_flags {
        flags.active = false;
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
                (activate_dialogue_runner, spawn_dialogue_runner)
                    .chain()
                    .run_if(in_state(GameState::Gaming).and_then(resource_exists::<YarnProject>)),
            )
            .add_systems(
                Update,
                (
                    deactivate_dialogue_runner.run_if(on_message::<PlayerStoppedChat>),
                    monitor_active_runners,
                ),
            )
            .add_systems(
                Update,
                hide_dialogue
                    .run_if(on_message::<PlayerStoppedChat>.or_else(on_message::<EndingTriggered>)),
            );
    }
}
