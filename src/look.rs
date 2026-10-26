//! Character looks: a folder with a `look.ron` manifest and one PNG strip per clip
//! (see openspec/changes/character-looks-and-sprite-format).

use std::collections::HashMap;
use std::f32::consts::PI;

use bevy::asset::{io::Reader, AssetLoader, LoadContext};
use bevy::prelude::*;
use serde::Deserialize;

use crate::animation::{CharacterAnim, SpriteAnimationClip, SpriteAnimator};

/// Cell size of every look strip, in px.
pub const LOOK_CELL: UVec2 = UVec2::new(128, 256);
/// Row inside a cell on which the feet stand.
pub const LOOK_FEET_ROW: u32 = 245;

const DEFAULT_FRAME_MS: u32 = 140;

// Used to make sure we always play up/down animation when a character moves diagonally.
const MOVEMENT_ANIMATION_ANGLE_BUFFER: f32 = 0.05;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Facing {
    Down,
    Left,
    Right,
    Up,
}

/// The four-way facing for a direction vector (zero faces left).
pub fn facing_of(dir: Vec2) -> Facing {
    let dir = if dir == Vec2::ZERO { Vec2::NEG_X } else { dir };
    let angle = Vec2::X.angle_to(dir);
    if (-3.0 / 4.0 * PI - MOVEMENT_ANIMATION_ANGLE_BUFFER
        ..=-1.0 / 4.0 * PI + MOVEMENT_ANIMATION_ANGLE_BUFFER)
        .contains(&angle)
    {
        Facing::Down
    } else if (1.0 / 4.0 * PI - MOVEMENT_ANIMATION_ANGLE_BUFFER
        ..=3.0 / 4.0 * PI + MOVEMENT_ANIMATION_ANGLE_BUFFER)
        .contains(&angle)
    {
        Facing::Up
    } else if !(-3.0 / 4.0 * PI..=3.0 / 4.0 * PI).contains(&angle) {
        Facing::Left
    } else {
        Facing::Right
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum ClipKind {
    Idle,
    Walk,
}

impl From<CharacterAnim> for ClipKind {
    /// Run is not part of the looks and resolves to Walk.
    fn from(anim: CharacterAnim) -> Self {
        match anim {
            CharacterAnim::Idle => ClipKind::Idle,
            CharacterAnim::Walk | CharacterAnim::Run => ClipKind::Walk,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ClipManifest {
    pub file: String,
    pub frames: u32,
    pub rows: Vec<Facing>,
    #[serde(default)]
    pub mirror_left: bool,
    #[serde(default = "default_frame_ms")]
    pub frame_ms: u32,
}

fn default_frame_ms() -> u32 {
    DEFAULT_FRAME_MS
}

impl ClipManifest {
    /// Strip row and horizontal flip that show `facing`, if this clip can.
    /// A drawn row wins over mirroring.
    fn row_for(&self, facing: Facing) -> Option<(usize, bool)> {
        if let Some(row) = self.rows.iter().position(|f| *f == facing) {
            return Some((row, false));
        }
        if facing == Facing::Left && self.mirror_left {
            return self
                .rows
                .iter()
                .position(|f| *f == Facing::Right)
                .map(|row| (row, true));
        }
        None
    }
}

/// Contents of a `look.ron`.
#[derive(Debug, Clone, Deserialize)]
#[serde(rename = "Look")]
pub struct LookManifest {
    pub id: String,
    pub character: String,
    pub cell: (u32, u32),
    pub clips: HashMap<ClipKind, ClipManifest>,
}

/// Which clip of which look to show.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ClipChoice {
    /// Taken from the default look instead of the character's current look.
    pub from_default: bool,
    pub kind: ClipKind,
    pub row: usize,
    pub flip: bool,
}

/// Resolution chain: the look's clip, the default look's clip, then `Idle` of the same
/// facing (look, then default). Walk facing up or down plays facing `horizontal`.
pub fn resolve_clip(
    look: &LookManifest,
    default: Option<&LookManifest>,
    kind: ClipKind,
    facing: Facing,
    horizontal: Facing,
) -> Option<ClipChoice> {
    let try_look = |manifest: &LookManifest, from_default: bool, kind: ClipKind| {
        let facing = match (kind, facing) {
            (ClipKind::Walk, Facing::Up | Facing::Down) => horizontal,
            _ => facing,
        };
        let (row, flip) = manifest.clips.get(&kind)?.row_for(facing)?;
        Some(ClipChoice {
            from_default,
            kind,
            row,
            flip,
        })
    };
    try_look(look, false, kind)
        .or_else(|| default.and_then(|d| try_look(d, true, kind)))
        .or_else(|| try_look(look, false, ClipKind::Idle))
        .or_else(|| default.and_then(|d| try_look(d, true, ClipKind::Idle)))
}

struct Strip {
    image: Handle<Image>,
    layout: Handle<TextureAtlasLayout>,
}

/// A loaded look: manifest plus the image and atlas layout of every strip.
#[derive(Asset, TypePath)]
pub struct Look {
    pub manifest: LookManifest,
    strips: HashMap<ClipKind, Strip>,
}

#[derive(Default, TypePath)]
pub struct LookLoader;

impl AssetLoader for LookLoader {
    type Asset = Look;
    type Settings = ();
    type Error = String;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _settings: &(),
        load_context: &mut LoadContext<'_>,
    ) -> Result<Look, String> {
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .await
            .map_err(|e| format!("Failed to read look: {e}"))?;
        let text = std::str::from_utf8(&bytes).map_err(|e| format!("Look is not UTF-8: {e}"))?;
        let manifest: LookManifest =
            ron::from_str(text).map_err(|e| format!("Failed to parse look: {e}"))?;

        let mut strips = HashMap::new();
        for (kind, clip) in &manifest.clips {
            if clip.frames == 0 || clip.rows.is_empty() {
                return Err(format!(
                    "Look {}: clip {kind:?} has no frames or rows",
                    manifest.id
                ));
            }
            let path = load_context
                .path()
                .resolve_embed_str(&clip.file)
                .map_err(|e| format!("Invalid clip path {}: {e}", clip.file))?;
            let layout = TextureAtlasLayout::from_grid(
                UVec2::new(manifest.cell.0, manifest.cell.1),
                clip.frames,
                clip.rows.len() as u32,
                None,
                None,
            );
            strips.insert(
                *kind,
                Strip {
                    image: load_context.load(path),
                    layout: load_context
                        .add_labeled_asset(format!("{}_{kind:?}", manifest.id), layout),
                },
            );
        }
        Ok(Look { manifest, strips })
    }

    fn extensions(&self) -> &[&str] {
        &["ron"]
    }
}

/// A character drawn from looks. Systems set the intent with [`CharacterLook::set_intent`]
/// and [`apply_looks`] updates sprite, atlas, flip and animator.
#[derive(Component)]
pub struct CharacterLook {
    look: Handle<Look>,
    default_look: Handle<Look>,
    anim: CharacterAnim,
    dir: Vec2,
    last_horizontal: Facing,
    applied: Option<(AssetId<Look>, ClipChoice)>,
}

impl CharacterLook {
    /// `look` is the current look, `default_look` the character's fallback look.
    pub fn new(look: Handle<Look>, default_look: Handle<Look>) -> Self {
        Self {
            look,
            default_look,
            anim: CharacterAnim::Idle,
            dir: Vec2::NEG_Y,
            last_horizontal: Facing::Right,
            applied: None,
        }
    }

    /// Switches to another look; image, layout, frame and flip reset together.
    #[allow(dead_code)]
    pub fn set_look(&mut self, look: Handle<Look>) {
        self.look = look;
    }

    pub fn set_intent(&mut self, dir: Vec2, anim: CharacterAnim) {
        self.dir = dir;
        self.anim = anim;
        if dir.x.abs() > 1e-3 {
            self.last_horizontal = if dir.x < 0.0 {
                Facing::Left
            } else {
                Facing::Right
            };
        }
    }
}

fn apply_looks(
    looks: Res<Assets<Look>>,
    mut q: Query<(&mut CharacterLook, &mut Sprite, &mut SpriteAnimator)>,
) {
    for (mut character, mut sprite, mut animator) in &mut q {
        let Some(look) = looks.get(&character.look) else {
            continue;
        };
        let default = looks.get(&character.default_look);
        let Some(choice) = resolve_clip(
            &look.manifest,
            default.map(|d| &d.manifest),
            character.anim.into(),
            facing_of(character.dir),
            character.last_horizontal,
        ) else {
            continue;
        };
        let source = if choice.from_default {
            character.default_look.id()
        } else {
            character.look.id()
        };
        if character.applied == Some((source, choice)) {
            continue;
        }
        let source_look = if choice.from_default {
            default
        } else {
            Some(look)
        };
        let Some(source_look) = source_look else {
            continue;
        };
        let (Some(strip), Some(clip)) = (
            source_look.strips.get(&choice.kind),
            source_look.manifest.clips.get(&choice.kind),
        ) else {
            continue;
        };

        let first = choice.row * clip.frames as usize;
        let seconds = clip.frames as f32 * clip.frame_ms as f32 / 1000.0;
        let anim_clip =
            SpriteAnimationClip::from_keyframe_range(first, first + clip.frames as usize, seconds);

        sprite.image = strip.image.clone();
        sprite.texture_atlas = Some(TextureAtlas {
            layout: strip.layout.clone(),
            index: anim_clip.first_frame,
        });
        sprite.flip_x = choice.flip;
        *animator = SpriteAnimator::looping(anim_clip);
        character.applied = Some((source, choice));
    }
}

pub struct LookPlugin;

impl Plugin for LookPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<Look>()
            .init_asset_loader::<LookLoader>()
            // Last: after the systems that set the intent (player state, NPC animation).
            .add_systems(Last, apply_looks.run_if(in_state(crate::GameState::Gaming)));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(ron_text: &str) -> LookManifest {
        ron::from_str(ron_text).unwrap()
    }

    const FULL: &str = include_str!("../assets/library/characters/looks/sam_casual/look.ron");
    const IDLE_ONLY: &str = r#"Look(id: "x", character: "samantha", cell: (128, 256), clips: {
        Idle: (file: "idle.png", frames: 1, rows: [Down, Left, Right, Up]),
    })"#;
    const RIGHT_ONLY_IDLE: &str = r#"Look(id: "y", character: "samantha", cell: (128, 256), clips: {
        Idle: (file: "idle.png", frames: 1, rows: [Down, Right, Up]),
        Walk: (file: "walk.png", frames: 4, rows: [Right], mirror_left: true),
    })"#;

    use ClipKind::*;
    use Facing::*;

    #[test]
    fn shipped_looks_parse() {
        for text in [
            FULL,
            include_str!("../assets/library/characters/looks/player_main/look.ron"),
            include_str!("../assets/library/characters/looks/sam_ponytail/look.ron"),
        ] {
            let look = parse(text);
            assert_eq!(look.cell, (LOOK_CELL.x, LOOK_CELL.y));
            assert!(look.clips.contains_key(&Idle) && look.clips.contains_key(&Walk));
        }
    }

    #[test]
    fn own_clip_wins_and_mirrors_left() {
        let look = parse(FULL);
        let c = resolve_clip(&look, None, Walk, Left, Left).unwrap();
        assert_eq!(
            (c.kind, c.row, c.flip, c.from_default),
            (Walk, 0, true, false)
        );
        let c = resolve_clip(&look, None, Walk, Right, Right).unwrap();
        assert!(!c.flip);
    }

    #[test]
    fn drawn_row_beats_mirroring() {
        let look = parse(FULL);
        let c = resolve_clip(&look, None, Idle, Left, Left).unwrap();
        assert_eq!((c.row, c.flip), (1, false));
    }

    #[test]
    fn idle_without_left_row_and_mirror_has_no_left() {
        let look = parse(RIGHT_ONLY_IDLE);
        let c = resolve_clip(&look, None, Idle, Left, Left);
        assert!(c.is_none());
    }

    #[test]
    fn vertical_walk_uses_last_horizontal() {
        let look = parse(FULL);
        let c = resolve_clip(&look, None, Walk, Up, Left).unwrap();
        assert_eq!((c.kind, c.flip), (Walk, true));
        let c = resolve_clip(&look, None, Walk, Down, Right).unwrap();
        assert_eq!((c.kind, c.flip), (Walk, false));
        // Standing still faces front or back.
        let c = resolve_clip(&look, None, Idle, Up, Left).unwrap();
        assert_eq!((c.kind, c.row), (Idle, 3));
    }

    #[test]
    fn missing_clip_falls_back_to_default_look_then_idle() {
        let idle_only = parse(IDLE_ONLY);
        let full = parse(FULL);
        let c = resolve_clip(&idle_only, Some(&full), Walk, Right, Right).unwrap();
        assert_eq!((c.kind, c.from_default), (Walk, true));
        let c = resolve_clip(&idle_only, None, Walk, Left, Left).unwrap();
        assert_eq!((c.kind, c.row, c.from_default), (Idle, 1, false));
    }

    #[test]
    fn facing_from_direction() {
        assert_eq!(facing_of(Vec2::NEG_Y), Down);
        assert_eq!(facing_of(Vec2::Y), Up);
        assert_eq!(facing_of(Vec2::X), Right);
        assert_eq!(facing_of(Vec2::NEG_X), Left);
        assert_eq!(facing_of(Vec2::ZERO), Left);
    }

    #[test]
    fn run_resolves_to_walk() {
        assert_eq!(ClipKind::from(CharacterAnim::Run), Walk);
    }
}
