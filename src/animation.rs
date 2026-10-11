//! Looping sprite-sheet animation.
//!
//! Hand-rolled system that drives `Sprite::texture_atlas.index` for
//! sprite-sheet animation clips.

use std::f32::consts::PI;
use std::time::Duration;

use bevy::prelude::*;

/// A single looping animation clip: an inclusive atlas frame range plus the total
/// loop duration. Frame indices refer to the entity's [`TextureAtlas`] layout.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct SpriteAnimationClip {
    /// First atlas frame index (inclusive).
    pub first_frame: usize,
    /// Last atlas frame index (inclusive).
    pub last_frame: usize,
    /// Total duration of one full loop, in seconds.
    pub duration: f32,
}

impl SpriteAnimationClip {
    /// Creates a clip from an exclusive keyframe range `(start, end)` plus total
    /// loop duration.
    pub const fn from_keyframe_range(start: usize, end: usize, duration: f32) -> Self {
        Self {
            first_frame: start,
            last_frame: if end > start { end - 1 } else { start },
            duration,
        }
    }

    /// Seconds per frame, used to tick the animator timer.
    pub fn seconds_per_frame(&self) -> f32 {
        let frames = (self.last_frame - self.first_frame + 1) as f32;
        self.duration / frames.max(1.0)
    }
}

/// Drives the atlas index of a sprite between `clip.first_frame` and
/// `clip.last_frame`, looping forever.
#[derive(Component, Clone, Debug)]
pub struct SpriteAnimator {
    pub clip: SpriteAnimationClip,
    frame_timer: Timer,
}

impl SpriteAnimator {
    pub fn looping(clip: SpriteAnimationClip) -> Self {
        Self {
            clip,
            frame_timer: Timer::new(
                Duration::from_secs_f32(clip.seconds_per_frame()),
                TimerMode::Repeating,
            ),
        }
    }

    /// Switches to a different clip, restarting the frame timer.
    pub fn play(&mut self, clip: SpriteAnimationClip) {
        if self.clip != clip {
            self.clip = clip;
            self.frame_timer = Timer::new(
                Duration::from_secs_f32(clip.seconds_per_frame()),
                TimerMode::Repeating,
            );
        }
    }
}

fn animate_sprites(time: Res<Time>, mut q_sprites: Query<(&mut SpriteAnimator, &mut Sprite)>) {
    for (mut animator, mut sprite) in &mut q_sprites {
        // Always keep the atlas index within the current clip's range, so that
        // clip switches (via SpriteAnimator::play) don't leave the index stuck
        // in the old clip's range.
        if let Some(atlas) = &mut sprite.texture_atlas {
            if atlas.index < animator.clip.first_frame || atlas.index > animator.clip.last_frame {
                atlas.index = animator.clip.first_frame;
            }
        }

        animator.frame_timer.tick(time.delta());
        if animator.frame_timer.just_finished() {
            if let Some(atlas) = &mut sprite.texture_atlas {
                atlas.index += 1;
                if atlas.index > animator.clip.last_frame {
                    atlas.index = animator.clip.first_frame;
                }
            }
        }
    }
}

pub struct SpriteAnimationPlugin;

impl Plugin for SpriteAnimationPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, animate_sprites);
    }
}

// ---------------------------------------------------------------------------
// Clip data
// ---------------------------------------------------------------------------

/// Animations of the 64x128 character sheets (player and wanderer):
/// `idle-down, idle-left, idle-right, idle-top, walking-*, running-*` (per direction).
pub const CHARACTER_CLIPS: [SpriteAnimationClip; 12] = [
    SpriteAnimationClip::from_keyframe_range(0, 8, 0.8), // idle-down
    SpriteAnimationClip::from_keyframe_range(10, 18, 0.8), // idle-left
    SpriteAnimationClip::from_keyframe_range(20, 28, 0.8), // idle-right
    SpriteAnimationClip::from_keyframe_range(30, 38, 0.8), // idle-top
    SpriteAnimationClip::from_keyframe_range(40, 50, 1.0), // walking-down
    SpriteAnimationClip::from_keyframe_range(50, 60, 1.0), // walking-left
    SpriteAnimationClip::from_keyframe_range(60, 70, 1.0), // walking-right
    SpriteAnimationClip::from_keyframe_range(70, 80, 1.0), // walking-top
    SpriteAnimationClip::from_keyframe_range(80, 88, 0.8), // running-down
    SpriteAnimationClip::from_keyframe_range(90, 98, 0.8), // running-left
    SpriteAnimationClip::from_keyframe_range(100, 108, 0.8), // running-right
    SpriteAnimationClip::from_keyframe_range(110, 118, 0.8), // running-top
];

pub const ELEONORE_IDLE: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 9, 0.9);
pub const JOTEM_IDLE: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 6, 0.6);
pub const ISABELLE_IDLE: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 7, 0.9);
pub const ANTONIUS_IDLE: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 5, 0.7);
pub const IONAS_IDLE: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 5, 0.55);

pub const DIALOGUE_START_HINT: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 2, 1.5);

/// Key icons: down/up/left/right and shift.
pub const KEY_ICON: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 2, 1.0);
pub const SHIFT_ICON: SpriteAnimationClip =
    SpriteAnimationClip::from_keyframe_range(0, 2, 3.5);

// ---------------------------------------------------------------------------
// Shared character clip selection
// ---------------------------------------------------------------------------

// Used to make sure we always play up/down animation when a character moves diagonally.
const MOVEMENT_ANIMATION_ANGLE_BUFFER: f32 = 0.05;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CharacterAnim {
    Idle,
    Walk,
    Run,
}

/// Picks the clip in [`CHARACTER_CLIPS`] for a facing direction and movement state.
pub fn character_clip(dir: Vec2, anim: CharacterAnim) -> SpriteAnimationClip {
    let dir = if dir == Vec2::ZERO { Vec2::NEG_X } else { dir };

    let angle = Vec2::X.angle_to(dir);
    let direction_index = if (-3.0 / 4.0 * PI - MOVEMENT_ANIMATION_ANGLE_BUFFER
        ..=-1.0 / 4.0 * PI + MOVEMENT_ANIMATION_ANGLE_BUFFER)
        .contains(&angle)
    {
        // Down
        0
    } else if (1.0 / 4.0 * PI - MOVEMENT_ANIMATION_ANGLE_BUFFER
        ..=3.0 / 4.0 * PI + MOVEMENT_ANIMATION_ANGLE_BUFFER)
        .contains(&angle)
    {
        // Up
        3
    } else if !(-3.0 / 4.0 * PI..=3.0 / 4.0 * PI).contains(&angle) {
        // Left
        1
    } else {
        // Right
        2
    };

    match anim {
        CharacterAnim::Idle => CHARACTER_CLIPS[direction_index],
        CharacterAnim::Walk => CHARACTER_CLIPS[4 + direction_index],
        CharacterAnim::Run => CHARACTER_CLIPS[8 + direction_index],
    }
}

/// Plays `clip`, setting the atlas index immediately when switching clips so the
/// sprite doesn't show a stale frame from the old clip until the next timer tick.
pub fn play_character_clip(
    animator: &mut SpriteAnimator,
    sprite: &mut Sprite,
    clip: SpriteAnimationClip,
) {
    if animator.clip != clip {
        if let Some(atlas) = &mut sprite.texture_atlas {
            atlas.index = clip.first_frame;
        }
    }
    animator.play(clip);
}
