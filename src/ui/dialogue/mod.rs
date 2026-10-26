pub mod runner;

mod command;
mod option_selection;
mod spawn;
mod speaker;
#[cfg(test)]
pub(crate) mod test;
mod typewriter;
mod updating;

pub use typewriter::Typewriter;

use bevy::prelude::*;

#[derive(Debug, Default)]
pub struct DialoguePlugin;

impl Plugin for DialoguePlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((
            spawn::DialogueSpawnPlugin,
            updating::DialogueUpdatingPlugin,
            option_selection::DialogueSelectionPlugin,
            typewriter::DialogueTypewriterPlugin,
            runner::DialogueRunnerPlugin,
        ));
    }
}

#[derive(Debug, Default, Clone, Copy, SystemSet, Eq, PartialEq, Hash)]
pub struct DialogueViewSystemSet;
