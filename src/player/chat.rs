use bevy::prelude::*;
use bevy_yarnspinner::prelude::*;

use crate::world::side_view::side_view;
use crate::{story::transition::scene_queued, ui::dialogue::runner::RunnerFlags, GameState};

use super::{input::PlayerInput, Player, PlayerState, NPC_PROXIMITY_DISTANCE};

/// Yarn node tag of scenes the player cannot leave with Escape.
const CUTSCENE_TAG: &str = "cutscene";

/// Anything the player can start a conversation with: an NPC or an interactable.
#[derive(Component)]
pub struct Talkable {
    /// The Yarn node the conversation starts at.
    pub node: String,
}

/// The talk target closest to `player` within `NPC_PROXIMITY_DISTANCE`, so that two
/// targets with overlapping ranges (such as two doors on one landing) never compete.
pub fn nearest_talkable<'a, T>(
    player: Vec2,
    talkables: impl IntoIterator<Item = (&'a Transform, T)>,
) -> Option<(&'a Transform, T)> {
    talkables
        .into_iter()
        .map(|(transform, t)| {
            let dist = player.distance_squared(transform.translation.xy());
            (dist, transform, t)
        })
        .filter(|(dist, ..)| *dist <= NPC_PROXIMITY_DISTANCE.powi(2))
        .min_by(|a, b| a.0.total_cmp(&b.0))
        .map(|(_, transform, t)| (transform, t))
}

#[derive(Message)]
pub struct PlayerStartedChat {
    pub node: String,
    pub direction: Vec2,
}
#[derive(Message)]
pub struct PlayerStoppedChat;

fn start_chat(
    player_input: Res<PlayerInput>,
    mut q_player: Query<(&Transform, &mut Player)>,
    q_talkables: Query<(&Transform, &Talkable), Without<Player>>,
    q_dialogue_runners: Query<&RunnerFlags, With<DialogueRunner>>,
    mut ev_player_started_chat: MessageWriter<PlayerStartedChat>,
) {
    if !player_input.dialogue {
        return;
    }
    for flags in &q_dialogue_runners {
        if flags.active {
            return;
        }
    }

    let (player_transform, mut player) = match q_player.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    let player_pos = player_transform.translation.xy();
    if let Some((transform, talkable)) = nearest_talkable(player_pos, q_talkables) {
        player.state = PlayerState::Talking;
        ev_player_started_chat.write(PlayerStartedChat {
            node: talkable.node.clone(),
            direction: transform.translation.xy() - player_pos,
        });
    }
}

/// Whether the active conversation is in a node tagged `cutscene`.
fn in_cutscene(q_runners: &Query<(&DialogueRunner, &RunnerFlags)>) -> bool {
    q_runners
        .iter()
        .filter(|(_, flags)| flags.active)
        .any(|(runner, _)| {
            runner
                .current_node()
                .and_then(|node| runner.get_tags_for_node(&node))
                .is_some_and(|tags| tags.iter().any(|tag| tag == CUTSCENE_TAG))
        })
}

fn stop_chat(
    player_input: Res<PlayerInput>,
    q_player: Query<&Player>,
    q_runners: Query<(&DialogueRunner, &RunnerFlags)>,
    mut ev_player_stopped_chat: MessageWriter<PlayerStoppedChat>,
) {
    let player = match q_player.single() {
        Ok(r) => r,
        Err(_) => return,
    };

    if !player_input.escape {
        return;
    }

    if player.state != PlayerState::Talking {
        return;
    }

    if in_cutscene(&q_runners) {
        return;
    }

    ev_player_stopped_chat.write(PlayerStoppedChat);
}

pub struct PlayerChatPlugin;

impl Plugin for PlayerChatPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<PlayerStartedChat>()
            .add_message::<PlayerStoppedChat>()
            .add_systems(
                Update,
                // A side-view room starts conversations by clicking its hotspots.
                (
                    start_chat.run_if(not(scene_queued).and_then(not(side_view))),
                    stop_chat,
                )
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}
