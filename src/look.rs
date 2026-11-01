//! Character looks: a folder with a `look.ron` manifest and either one PNG strip per clip
//! (see openspec/changes/character-looks-and-sprite-format) or one `.aseprite` file whose
//! tags are named `<clip>_<facing>` (for example `walk_right`), drawn by bevy_aseprite_ultra.

use std::collections::HashMap;
use std::f32::consts::PI;

use bevy::asset::{io::Reader, AssetLoader, LoadContext};
use bevy::prelude::*;
use bevy_aseprite_ultra::prelude::{Animation, AseAnimation, Aseprite};
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
    /// PNG strip; unused when the look has an `aseprite` file.
    #[serde(default, deserialize_with = "some_string")]
    pub file: Option<String>,
    /// Frames per row of the strip; unused when the look has an `aseprite` file.
    #[serde(default)]
    pub frames: u32,
    pub rows: Vec<Facing>,
    #[serde(default)]
    pub mirror_left: bool,
    #[serde(default = "default_frame_ms")]
    pub frame_ms: u32,
}

/// Optional string fields written as plain strings (`file: "idle.png"`, not `Some(...)`).
fn some_string<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Option<String>, D::Error> {
    String::deserialize(d).map(Some)
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
    /// The look's `.aseprite` file. Frames, timing and tags then come from it, and each
    /// clip row plays the tag [`tag_name`]`(kind, facing)`.
    #[serde(default, deserialize_with = "some_string")]
    pub aseprite: Option<String>,
    pub clips: HashMap<ClipKind, ClipManifest>,
}

/// Aseprite tag of a clip facing one way: `idle_down`, `walk_right`, ...
pub fn tag_name(kind: ClipKind, facing: Facing) -> String {
    format!("{kind:?}_{facing:?}").to_lowercase()
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

/// A loaded look: manifest plus either its Aseprite file or the image and atlas layout of
/// every strip.
#[derive(Asset, TypePath)]
pub struct Look {
    pub manifest: LookManifest,
    aseprite: Option<Handle<Aseprite>>,
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

        if let Some(file) = &manifest.aseprite {
            if let Some((kind, _)) = manifest.clips.iter().find(|(_, c)| c.rows.is_empty()) {
                return Err(format!("Look {}: clip {kind:?} has no rows", manifest.id));
            }
            let path = load_context
                .path()
                .resolve_embed_str(file)
                .map_err(|e| format!("Invalid aseprite path {file}: {e}"))?;
            return Ok(Look {
                aseprite: Some(load_context.load(path)),
                manifest,
                strips: HashMap::new(),
            });
        }

        let mut strips = HashMap::new();
        for (kind, clip) in &manifest.clips {
            let Some(file) = clip.file.as_deref() else {
                return Err(format!("Look {}: clip {kind:?} has no file", manifest.id));
            };
            if clip.frames == 0 || clip.rows.is_empty() {
                return Err(format!(
                    "Look {}: clip {kind:?} has no frames or rows",
                    manifest.id
                ));
            }
            let path = load_context
                .path()
                .resolve_embed_str(file)
                .map_err(|e| format!("Invalid clip path {file}: {e}"))?;
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
        Ok(Look {
            manifest,
            aseprite: None,
            strips,
        })
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
    mut commands: Commands,
    looks: Res<Assets<Look>>,
    mut q: Query<(
        Entity,
        &mut CharacterLook,
        &mut Sprite,
        &mut SpriteAnimator,
        Has<AseAnimation>,
    )>,
) {
    for (entity, mut character, mut sprite, mut animator, has_ase) in &mut q {
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
        let Some(clip) = source_look.manifest.clips.get(&choice.kind) else {
            continue;
        };

        if let Some(aseprite) = &source_look.aseprite {
            // bevy_aseprite_ultra sets image and atlas; `animate_sprites` skips this entity.
            let tag = tag_name(choice.kind, clip.rows[choice.row]);
            commands.entity(entity).insert(AseAnimation {
                aseprite: aseprite.clone(),
                animation: Animation::tag(&tag),
            });
            sprite.flip_x = choice.flip;
            character.applied = Some((source, choice));
            continue;
        }
        if has_ase {
            commands.entity(entity).remove::<AseAnimation>();
        }

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
        app.add_plugins(bevy_aseprite_ultra::AsepriteUltraPlugin)
            .init_asset::<Look>()
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

    const FULL: &str = include_str!("../assets/library/characters/looks/player_main/look.ron");
    const ASE: &str = include_str!("../assets/library/characters/looks/sam_casual/look.ron");
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
            ASE,
            include_str!("../assets/library/characters/looks/sam_ponytail/look.ron"),
        ] {
            let look = parse(text);
            assert_eq!(look.cell, (LOOK_CELL.x, LOOK_CELL.y));
            assert!(look.clips.contains_key(&Idle) && look.clips.contains_key(&Walk));
        }
    }

    /// Every tag an aseprite look can resolve to exists in its file, and the canvas is one cell.
    #[test]
    fn aseprite_looks_have_their_tags() {
        use aseprite_loader::loader::{AsepriteFile, LayerSelection};
        let dir = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/library/characters/looks"
        );
        for entry in std::fs::read_dir(dir).unwrap() {
            let folder = entry.unwrap().path();
            let look = parse(&std::fs::read_to_string(folder.join("look.ron")).unwrap());
            let Some(file) = &look.aseprite else { continue };
            let bytes = std::fs::read(folder.join(file)).unwrap();
            let ase = AsepriteFile::load(&bytes).unwrap();
            assert_eq!(
                ase.size(),
                (LOOK_CELL.x as u16, LOOK_CELL.y as u16),
                "{file}"
            );
            for facing in [Down, Left, Right, Up] {
                for kind in [Idle, Walk] {
                    let Some(c) = resolve_clip(&look, None, kind, facing, Right) else {
                        continue;
                    };
                    let tag = tag_name(c.kind, look.clips[&c.kind].rows[c.row]);
                    let t = ase.tags().iter().find(|t| t.name == tag);
                    let t = t.unwrap_or_else(|| panic!("{file}: no tag {tag}"));
                    // Every frame of the tag draws something.
                    for frame in t.range.clone() {
                        let mut buf = vec![0u8; (LOOK_CELL.x * LOOK_CELL.y * 4) as usize];
                        ase.render_frame(frame as usize, &mut buf, &LayerSelection::All)
                            .unwrap();
                        assert!(
                            buf.chunks(4).any(|p| p[3] > 0),
                            "{file}: frame {frame} empty"
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn aseprite_look_tags() {
        let look = parse(ASE);
        assert_eq!(look.aseprite.as_deref(), Some("sam_casual.aseprite"));
        let c = resolve_clip(&look, None, Walk, Left, Left).unwrap();
        assert_eq!(
            tag_name(c.kind, look.clips[&c.kind].rows[c.row]),
            "walk_right"
        );
        assert!(c.flip);
        let c = resolve_clip(&look, None, Idle, Up, Left).unwrap();
        assert_eq!(tag_name(c.kind, look.clips[&c.kind].rows[c.row]), "idle_up");
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
