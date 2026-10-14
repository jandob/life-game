//! The one place that knows who speaks: portrait and typewriter speed per speaker.

use std::str::FromStr;

use bevy::prelude::*;

use crate::npc::NpcDialogue;
use crate::GameAssets;

/// Typewriter speed (graphemes per second) of names that are not in the table.
pub const AVERAGE_SPEED: f32 = 20.0;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Speaker {
    Player,
    Npc(NpcDialogue),
}

/// Looks up the speaker by the Yarn character name. A leading `_` (the "???" name
/// of a character the player has not met) is ignored.
pub fn speaker(raw_name: &str) -> Option<Speaker> {
    match raw_name.trim_start_matches('_') {
        "You" => Some(Speaker::Player),
        name => NpcDialogue::from_str(name).ok().map(Speaker::Npc),
    }
}

pub fn portrait(assets: &GameAssets, speaker: Speaker) -> Handle<Image> {
    match speaker {
        Speaker::Player => assets.player_icon.clone(),
        Speaker::Npc(NpcDialogue::Samantha) => assets.samantha_icon.clone(),
    }
}

pub fn writer_speed(speaker: Option<Speaker>) -> f32 {
    match speaker {
        Some(Speaker::Player) => 20.0,
        Some(Speaker::Npc(NpcDialogue::Samantha)) => 20.0,
        None => AVERAGE_SPEED,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn speakers_are_found_by_yarn_name() {
        assert_eq!(speaker("You"), Some(Speaker::Player));
        assert_eq!(
            speaker("Samantha"),
            Some(Speaker::Npc(NpcDialogue::Samantha))
        );
        assert_eq!(
            speaker("_Samantha"),
            Some(Speaker::Npc(NpcDialogue::Samantha))
        );
    }

    #[test]
    fn unknown_names_keep_the_average_speed() {
        assert_eq!(speaker("Nobody"), None);
        assert_eq!(speaker(""), None);
        assert_eq!(writer_speed(None), AVERAGE_SPEED);
    }
}
