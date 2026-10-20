//! The player's phone: text conversations and notes.
//!
//! - `<<phone NODE>>` delivers a text conversation: NODE (tagged `phone`) waits until the
//!   player opens the phone, then plays in the dialogue box. Lines of `phone` nodes are
//!   kept in the message history.
//! - `<<note ID "TEXT">>` adds an open note (or updates its text), `<<note_done ID>>`
//!   ticks it off. Notes are the quest log.

use std::collections::VecDeque;

use bevy::prelude::*;
use bevy_yarnspinner::events::{DialogueCompleted, PresentLine};
use bevy_yarnspinner::prelude::*;

use crate::ui::dialogue::runner::RunnerFlags;
use crate::GameState;

/// Yarn node tag of text conversations.
pub const PHONE_TAG: &str = "phone";

pub struct Message {
    pub speaker: String,
    pub text: String,
}

pub struct Note {
    pub id: String,
    pub text: String,
    pub done: bool,
}

#[derive(Resource, Default)]
pub struct Phone {
    /// Lines of text conversations already read, oldest first.
    pub messages: Vec<Message>,
    /// In the order they were added.
    pub notes: Vec<Note>,
    /// Text conversations delivered but not read yet, oldest first.
    pub unread: VecDeque<String>,
}

impl Phone {
    pub fn deliver(&mut self, node: String) {
        if !self.unread.contains(&node) {
            self.unread.push_back(node);
        }
    }

    pub fn note(&mut self, id: String, text: String) {
        match self.notes.iter_mut().find(|note| note.id == id) {
            Some(note) => {
                note.text = text;
                note.done = false;
            }
            None => self.notes.push(Note {
                id,
                text,
                done: false,
            }),
        }
    }

    pub fn note_done(&mut self, id: &str) {
        match self.notes.iter_mut().find(|note| note.id == id) {
            Some(note) => note.done = true,
            None => warn!("note_done: no note '{id}'"),
        }
    }

    /// Open notes first, then done ones, each in the order they were added.
    pub fn sorted_notes(&self) -> impl Iterator<Item = &Note> {
        let open = self.notes.iter().filter(|note| !note.done);
        open.chain(self.notes.iter().filter(|note| note.done))
    }
}

/// `<<phone NODE>>`
pub fn phone_command(In(node): In<String>, mut phone: ResMut<Phone>) {
    phone.deliver(node);
}

/// `<<note ID "TEXT">>`
pub fn note_command(In((id, text)): In<(String, String)>, mut phone: ResMut<Phone>) {
    phone.note(id, text);
}

/// `<<note_done ID>>`
pub fn note_done_command(In(id): In<String>, mut phone: ResMut<Phone>) {
    phone.note_done(&id);
}

/// Keeps the lines of text conversations in the history.
fn log_phone_line(
    trigger: On<PresentLine>,
    q_runners: Query<&DialogueRunner>,
    mut phone: ResMut<Phone>,
) {
    let event = trigger.event();
    let Ok(runner) = q_runners.get(event.entity) else {
        return;
    };
    if !in_phone_node(runner) {
        return;
    }
    let speaker = event.line.character_name().unwrap_or_default();
    phone.messages.push(Message {
        speaker: speaker.trim_start_matches('_').to_string(),
        text: event.line.text_without_character_name(),
    });
}

/// A text stays unread until its conversation has completed, so one left with Escape
/// halfway is resumed by the next P.
fn mark_text_read(
    trigger: On<DialogueCompleted>,
    q_flags: Query<&RunnerFlags>,
    mut phone: ResMut<Phone>,
) {
    let Ok(flags) = q_flags.get(trigger.event().entity) else {
        return;
    };
    phone.unread.retain(|node| *node != flags.node);
}

/// Whether the runner is playing a text conversation.
pub fn in_phone_node(runner: &DialogueRunner) -> bool {
    runner
        .current_node()
        .and_then(|node| runner.get_tags_for_node(&node))
        .is_some_and(|tags| tags.iter().any(|tag| tag == PHONE_TAG))
}

fn reset_phone(mut commands: Commands) {
    commands.insert_resource(Phone::default());
}

pub struct PhonePlugin;

impl Plugin for PhonePlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Phone>()
            .add_observer(log_phone_line)
            .add_observer(mark_text_read)
            .add_systems(OnExit(GameState::MainMenu), reset_phone);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn notes_update_and_sort() {
        let mut phone = Phone::default();
        phone.note("a".into(), "First".into());
        phone.note("b".into(), "Second".into());
        phone.note_done("a");
        phone.note("b".into(), "Second, changed".into());
        let texts: Vec<_> = phone.sorted_notes().map(|n| n.text.as_str()).collect();
        assert_eq!(texts, ["Second, changed", "First"]);
    }

    #[test]
    fn a_text_is_delivered_once() {
        let mut phone = Phone::default();
        phone.deliver("T".into());
        phone.deliver("T".into());
        assert_eq!(phone.unread.len(), 1);
    }
}
