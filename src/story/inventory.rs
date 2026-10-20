//! The player's items. An item is a Yarn bool variable `$item_<id>`, declared in
//! `assets/dialogue/items.yarn`: the story gives and takes items with `<<set>>` and checks
//! them in conditions, and they persist like every other story variable. The table here
//! adds what Yarn can't hold: the name and description the inventory shows.

use std::collections::HashSet;

use bevy::prelude::*;
use bevy_yarnspinner::default_impl::MemoryVariableStorage;
use bevy_yarnspinner::prelude::*;

use super::StoryVars;
use crate::GameState;

pub struct Item {
    pub id: &'static str,
    pub name: &'static str,
    pub about: &'static str,
}

/// Every item, in the order the inventory lists them. Each needs a matching
/// `<<declare $item_<id> = false>>` in `items.yarn`.
pub const ITEMS: &[Item] = &[
    Item {
        id: "blush_socks",
        name: "Blush socks",
        about: "A matching pair, for once. From Samantha.",
    },
    Item {
        id: "bakery_bag",
        name: "Bakery bag",
        about: "One plain croissant. Still warm.",
    },
    Item {
        id: "wine_fox",
        name: "Red Fox 2021",
        about: "A red with a fox on the label. No gold.",
    },
    Item {
        id: "wine_reserve",
        name: "Red Fox Reserve",
        about: "The same fox, with a gold label and a higher price.",
    },
    Item {
        id: "wine_house",
        name: "House red",
        about: "The cheapest red in the shop. It says so on the sticker.",
    },
    Item {
        id: "tulips",
        name: "Tulips",
        about: "A bunch of five, yellow and red.",
    },
    Item {
        id: "chocolates",
        name: "Sea salt chocolate",
        about: "Dark, with sea salt. The fancy bar.",
    },
    Item {
        id: "corkscrew",
        name: "Her corkscrew",
        about: "From the drawer by her sink.",
    },
];

/// The Yarn variable of an item.
pub fn variable(id: &str) -> String {
    format!("$item_{id}")
}

/// The items the player carries, in table order.
pub fn carried(storage: &MemoryVariableStorage) -> Vec<&'static Item> {
    ITEMS
        .iter()
        .filter(|item| {
            storage
                .get(&variable(item.id))
                .is_ok_and(|value| matches!(value, YarnValue::Boolean(true)))
        })
        .collect()
}

/// Sent when the player gets an item during play.
#[derive(Message)]
pub struct ItemGained(pub &'static Item);

/// The items carried at the last check, to notice new ones.
#[derive(Resource, Default)]
pub struct ItemsSeen(HashSet<&'static str>);

impl ItemsSeen {
    /// Takes the current items as known, so they aren't announced (e.g. after a start
    /// point).
    pub fn rebaseline(&mut self, storage: &MemoryVariableStorage) {
        self.0 = carried(storage).iter().map(|item| item.id).collect();
    }
}

fn notice_new_items(
    story_vars: Res<StoryVars>,
    mut seen: ResMut<ItemsSeen>,
    mut ev_item_gained: MessageWriter<ItemGained>,
) {
    let now = carried(&story_vars.0);
    for item in &now {
        if !seen.0.contains(item.id) {
            ev_item_gained.write(ItemGained(item));
        }
    }
    seen.0 = now.iter().map(|item| item.id).collect();
}

fn reset_items_seen(mut seen: ResMut<ItemsSeen>) {
    seen.0.clear();
}

pub struct InventoryPlugin;

impl Plugin for InventoryPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<ItemsSeen>()
            .add_message::<ItemGained>()
            .add_systems(OnExit(GameState::MainMenu), reset_items_seen)
            .add_systems(Update, notice_new_items.run_if(in_state(GameState::Gaming)));
    }
}
