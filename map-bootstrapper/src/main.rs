//! Bootstrap tool: runs the current procedural generation for a bounded region
//! and exports the result as a Tiled `.tmj` map file with `.tsj` tileset.
//!
//! This is a temporary tool — after the initial map is generated, both the tool
//! and the procedural generation code it depends on are deleted from the workspace.

use std::collections::HashSet;
use std::f32::consts::PI;
use std::path::Path;

use glam::{IVec2, Vec2, Vec3};
use chrono::Timelike;
use noisy_bevy::simplex_noise_2d_seeded;
use rand::{Rng, SeedableRng};
use rand_xoshiro::Xoshiro256PlusPlus;
use serde::Serialize;

// ──────────────────────────────────────────────────────────────────────
// Constants (mirrored from the game's generation module)
// ──────────────────────────────────────────────────────────────────────

const TILE_SIZE: f32 = 16.0;
const CHUNK_SIZE: u32 = 16;
const RENDERED_CHUNKS_RADIUS: u32 = 3;
const MAP_WIDTH: u32 = 100;
const MAP_HEIGHT: u32 = 100;

const NOISE_ZOOM: f32 = 0.02;
const FLOWER_NOISE_ZOOM: f32 = 0.1;
const WATER_SPARKLE_NOISE_ZOOM: f32 = 0.1;
const WATER_HEIGH_LEVEL: f32 = -0.5;
const FLOWER_HEIGHT_LEVEL: f32 = -0.7;
const WATER_SPARKLE_HEIGHT_LEVEL_MAX: f32 = -0.6;
const WATER_SPARKLE_HEIGHT_LEVEL_MIN: f32 = -0.85;

const EMPTY_TYPE_MASK: u8 = 1 << 0;
const WATER_TYPE_MASK: u8 = 1 << 1;
const GRASS_TYPE_MASK: u8 = 1 << 2;
const PATH_TYPE_MASK: u8 = 1 << 3;
const WATER_SPARKLE_TYPE_MASK: u8 = 1 << 4;
const INVALID_TILE: u16 = 15 * 16;

const BITMASK_TOP_RIGHT: u16 = 1 << 0;
const BITMASK_BOT_RIGHT: u16 = 1 << 1;
const BITMASK_BOT_LEFT: u16 = 1 << 2;
const BITMASK_TOP_LEFT: u16 = 1 << 3;

const GRASS_FLOWER_SUPER_POSITION: u16 = 15;

const START_FILL_RADIUS: i32 = 15;

const DISK_RADIUS: f32 = 35.0;
const REGION_SIZE: Vec2 = Vec2::new(120.0, 120.0);
const POISSON_REJECTION_ITER: usize = 20;
const SAMPLE_RATE: usize = 3 * DISK_RADIUS as usize;

// ──────────────────────────────────────────────────────────────────────
// BitMasks (mirrored from bitmask.rs)
// ──────────────────────────────────────────────────────────────────────

fn grid_to_index(x: u16, y: u16) -> u16 {
    x + y * 16
}

struct BitMasks {
    masks: Vec<(u16, Vec<u16>)>,
}

impl BitMasks {
    fn grass() -> Self {
        Self {
            masks: vec![
                (
                    0,
                    vec![
                        grid_to_index(11, 13),
                        grid_to_index(12, 13),
                        grid_to_index(13, 13),
                        grid_to_index(12, 14),
                        grid_to_index(13, 14),
                    ],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(0, 1)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT,
                    vec![grid_to_index(5, 0)],
                ),
                (
                    BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(8, 0)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(8, 2)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(5, 2)],
                ),
                (
                    BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT,
                    vec![grid_to_index(6, 0), grid_to_index(7, 0)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(6, 2), grid_to_index(7, 2)],
                ),
                (
                    BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(7, 1), grid_to_index(8, 1)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT,
                    vec![grid_to_index(5, 1), grid_to_index(6, 1)],
                ),
                (BITMASK_BOT_RIGHT, vec![grid_to_index(5, 3)]),
                (BITMASK_BOT_LEFT, vec![grid_to_index(6, 3)]),
                (BITMASK_TOP_LEFT, vec![grid_to_index(6, 4)]),
                (BITMASK_TOP_RIGHT, vec![grid_to_index(5, 4)]),
                (
                    BITMASK_TOP_LEFT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(7, 3)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_RIGHT,
                    vec![grid_to_index(7, 4)],
                ),
            ],
        }
    }

    fn path() -> Self {
        Self {
            masks: vec![
                (0, vec![GRASS_FLOWER_SUPER_POSITION]),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(2, 1)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT,
                    vec![grid_to_index(1, 3)],
                ),
                (
                    BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(2, 3)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(2, 4)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(1, 4)],
                ),
                (
                    BITMASK_TOP_LEFT | BITMASK_TOP_RIGHT,
                    vec![grid_to_index(2, 2), grid_to_index(4, 5)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(2, 0), grid_to_index(3, 5)],
                ),
                (
                    BITMASK_TOP_RIGHT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(1, 1), grid_to_index(2, 5)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_LEFT,
                    vec![grid_to_index(3, 1), grid_to_index(1, 5)],
                ),
                (BITMASK_BOT_RIGHT, vec![grid_to_index(1, 0)]),
                (BITMASK_BOT_LEFT, vec![grid_to_index(3, 0)]),
                (BITMASK_TOP_LEFT, vec![grid_to_index(3, 2)]),
                (BITMASK_TOP_RIGHT, vec![grid_to_index(1, 2)]),
                (
                    BITMASK_TOP_LEFT | BITMASK_BOT_RIGHT,
                    vec![grid_to_index(3, 4)],
                ),
                (
                    BITMASK_BOT_LEFT | BITMASK_TOP_RIGHT,
                    vec![grid_to_index(3, 3)],
                ),
            ],
        }
    }

    fn flower() -> Self {
        Self {
            masks: vec![
                (
                    0,
                    vec![
                        grid_to_index(0, 1),
                        grid_to_index(0, 2),
                        grid_to_index(0, 3),
                        grid_to_index(0, 4),
                    ],
                ),
                (
                    1,
                    vec![
                        grid_to_index(0, 6),
                        grid_to_index(1, 6),
                        grid_to_index(2, 6),
                        grid_to_index(3, 6),
                        grid_to_index(0, 7),
                        grid_to_index(1, 7),
                        grid_to_index(2, 7),
                        grid_to_index(3, 7),
                    ],
                ),
            ],
        }
    }

    fn get_index(&self, mask: u16) -> u16 {
        let mut rng = rand::thread_rng();
        for (key, indices) in &self.masks {
            if *key == mask {
                return indices[rng.gen_range(0..indices.len())];
            }
        }
        INVALID_TILE
    }
}

// ──────────────────────────────────────────────────────────────────────
// BitMap (simplified, mirrors bitmap.rs for bootstrap use)
// ──────────────────────────────────────────────────────────────────────

#[derive(Clone, Copy, PartialEq)]
enum TileType {
    GrassWater,
    PathOrGrass,
}

struct BitMap {
    seed: f32,
    vertices: Vec<Vec2>,
    edges: HashSet<(usize, usize)>,
    grass_mask: BitMasks,
    path_mask: BitMasks,
    flower_mask: BitMasks,
    // For a bounded 100×100 map we use a single flat array
    tiles: Vec<(u8, u16)>,
    width: usize,
    height: usize,
    origin_x: i32,
    origin_y: i32,
}

impl BitMap {
    fn new(origin_x: i32, origin_y: i32, width: usize, height: usize) -> Self {
        Self {
            seed: chrono::Utc::now().nanosecond() as f32,
            vertices: Vec::new(),
            edges: HashSet::new(),
            grass_mask: BitMasks::grass(),
            path_mask: BitMasks::path(),
            flower_mask: BitMasks::flower(),
            tiles: vec![(EMPTY_TYPE_MASK, INVALID_TILE); width * height],
            width,
            height,
            origin_x,
            origin_y,
        }
    }

    fn idx(&self, v: IVec2) -> Option<usize> {
        let x = (v.x - self.origin_x) as isize;
        let y = (v.y - self.origin_y) as isize;
        if x < 0 || y < 0 || x >= self.width as isize || y >= self.height as isize {
            return None;
        }
        Some(y as usize * self.width + x as usize)
    }

    fn get_tile_raw(&self, v: IVec2) -> (u8, u16) {
        self.idx(v).map(|i| self.tiles[i]).unwrap_or((EMPTY_TYPE_MASK, INVALID_TILE))
    }

    fn get_tile_mut(&mut self, v: IVec2) -> Option<&mut (u8, u16)> {
        self.idx(v).map(move |i| &mut self.tiles[i])
    }

    fn get_type_flag(&self, v: IVec2, mask: u8) -> bool {
        self.get_tile_raw(v).0 & mask == mask
    }

    fn set_type_flag(&mut self, v: IVec2, mask: u8) {
        if let Some(tile) = self.get_tile_mut(v) {
            tile.0 |= mask;
        }
    }

    fn set_tileset(&mut self, v: IVec2, tile: u16) {
        if let Some(t) = self.get_tile_mut(v) {
            t.1 = tile;
        }
    }

    fn water_height(&self, v: IVec2) -> f32 {
        let w = Vec2::new(v.x as f32, v.y as f32);
        let noise = simplex_noise_2d_seeded(w * NOISE_ZOOM, self.seed);
        let secondary_noise = simplex_noise_2d_seeded(w * NOISE_ZOOM, self.seed + 1.0) * 1.0;
        noise + secondary_noise
    }

    fn water_sparkle_height(&self, v: IVec2) -> f32 {
        let w = Vec2::new(v.x as f32, v.y as f32);
        let noise = simplex_noise_2d_seeded(w * WATER_SPARKLE_NOISE_ZOOM, self.seed);
        let secondary_noise =
            simplex_noise_2d_seeded(w * WATER_SPARKLE_NOISE_ZOOM, self.seed + 1.0) * 1.0;
        noise + secondary_noise
    }

    fn collapse_water(&mut self, v: IVec2) -> bool {
        if self.get_type_flag(v, EMPTY_TYPE_MASK) == false {
            return self.get_type_flag(v, WATER_TYPE_MASK);
        }

        let height = self.water_height(v);
        let is_water = height < WATER_HEIGH_LEVEL;
        if is_water {
            self.set_type_flag(v, WATER_TYPE_MASK);
            if !(WATER_SPARKLE_HEIGHT_LEVEL_MIN..=WATER_SPARKLE_HEIGHT_LEVEL_MAX).contains(&height)
                && self.water_sparkle_height(v) < 0.0
            {
                self.set_type_flag(v, WATER_SPARKLE_TYPE_MASK);
            }
        } else {
            self.set_type_flag(v, GRASS_TYPE_MASK);
        }
        is_water
    }

    fn neigbhor_bitmask_grass(&mut self, v: IVec2) -> u16 {
        let mut mask = 0u16;
        mask |= BITMASK_BOT_LEFT * !self.collapse_water(v) as u16;
        mask |= BITMASK_TOP_LEFT * !self.collapse_water(v + IVec2::new(0, 1)) as u16;
        mask |= BITMASK_TOP_RIGHT * !self.collapse_water(v + IVec2::new(1, 1)) as u16;
        mask |= BITMASK_BOT_RIGHT * !self.collapse_water(v + IVec2::new(1, 0)) as u16;
        mask
    }

    fn neigbhor_bitmask_path(&mut self, v: IVec2) -> u16 {
        let mut mask = 0u16;
        mask |= BITMASK_BOT_LEFT * self.get_type_flag(v, PATH_TYPE_MASK) as u16;
        mask |= BITMASK_TOP_LEFT * self.get_type_flag(v + IVec2::new(0, 1), PATH_TYPE_MASK) as u16;
        mask |= BITMASK_TOP_RIGHT * self.get_type_flag(v + IVec2::new(1, 1), PATH_TYPE_MASK) as u16;
        mask |= BITMASK_BOT_RIGHT * self.get_type_flag(v + IVec2::new(1, 0), PATH_TYPE_MASK) as u16;
        mask
    }

    fn tile_type(&mut self, v: IVec2) -> TileType {
        let has_water = self.collapse_water(v)
            | self.collapse_water(v + IVec2::new(0, 1))
            | self.collapse_water(v + IVec2::new(1, 1))
            | self.collapse_water(v + IVec2::new(1, 0));
        if has_water {
            TileType::GrassWater
        } else {
            TileType::PathOrGrass
        }
    }

    fn get_flower_tile(&self, v: IVec2) -> u16 {
        let w = Vec2::new(v.x as f32, v.y as f32);
        let noise = simplex_noise_2d_seeded(w * FLOWER_NOISE_ZOOM, self.seed + 2.0);
        let secondary_noise =
            simplex_noise_2d_seeded(w * FLOWER_NOISE_ZOOM, self.seed + 3.0) * 1.0;
        let h = noise + secondary_noise;
        if h < FLOWER_HEIGHT_LEVEL {
            self.flower_mask.get_index(1)
        } else {
            self.flower_mask.get_index(0)
        }
    }

    fn collapse_tile(&mut self, v: IVec2) {
        let tile = match self.tile_type(v) {
            TileType::GrassWater => {
                let t = self.neigbhor_bitmask_grass(v);
                self.grass_mask.get_index(t)
            }
            TileType::PathOrGrass => {
                let t = self.neigbhor_bitmask_path(v);
                self.path_mask.get_index(t)
            }
        };

        if tile == GRASS_FLOWER_SUPER_POSITION {
            self.set_tileset(v, self.get_flower_tile(v));
        } else {
            self.set_tileset(v, tile);
        }
    }

    fn get_tile_index(&mut self, v: IVec2) -> u16 {
        self.collapse_water(v);
        self.collapse_tile(v);
        self.get_tile_raw(v).1
    }
}

// ──────────────────────────────────────────────────────────────────────
// Graph functions (mirrored from graph.rs)
// ──────────────────────────────────────────────────────────────────────

fn generate_edges(vertices: &[Vec2]) -> Vec<(usize, usize)> {
    let mut edges = Vec::new();
    for i in 0..vertices.len() {
        for j in 0..vertices.len() {
            if i >= j {
                continue;
            }
            edges.push((i, j, vertices[i].distance_squared(vertices[j])));
        }
    }
    edges.sort_by(|a, b| a.2.partial_cmp(&b.2).unwrap());
    edges.into_iter().map(|(a, b, _)| (a, b)).collect()
}

fn kruskals_edges(vertices: &[Vec2]) -> HashSet<(usize, usize)> {
    let sorted_edges = generate_edges(vertices);
    let mut result = HashSet::new();
    let mut sets: Vec<HashSet<usize>> = (0..vertices.len()).map(|i| {
        let mut s = HashSet::new();
        s.insert(i);
        s
    }).collect();

    for (u, v) in sorted_edges {
        let mut u_set_index = None;
        let mut v_set_index = None;

        for (index, set) in sets.iter().enumerate() {
            if set.contains(&u) {
                u_set_index = Some(index);
            }
            if set.contains(&v) {
                v_set_index = Some(index);
            }
            if u_set_index.is_some() && v_set_index.is_some() {
                break;
            }
        }

        if let (Some(u_index), Some(v_index)) = (u_set_index, v_set_index) {
            if u_index != v_index {
                result.insert((u, v));
                let other = sets[v_index].clone();
                let u_set = &mut sets[u_index];
                u_set.extend(other);
                sets.remove(v_index);
            }
        }
    }
    result
}

fn connect_outer_vertices(vertices: &[Vec2], edges: &mut HashSet<(usize, usize)>) {
    if vertices.len() < 2 {
        return;
    }

    fn number_of_edges(vertex_index: usize, edges: &HashSet<(usize, usize)>) -> usize {
        edges.iter().filter(|&&(a, b)| a == vertex_index || b == vertex_index).count()
    }

    for i in 0..vertices.len() {
        if number_of_edges(i, edges) > 1 {
            continue;
        }

        let mut best_vertex_index = if i == 0 { 1 } else { 0 };
        let mut best_loss = f32::MAX;

        for j in 0..vertices.len() {
            if j == i {
                continue;
            }
            if edges.contains(&(i, j)) || edges.contains(&(j, i)) {
                continue;
            }
            let loss = vertices[i].distance_squared(vertices[j]) / vertices[j].length_squared();
            if loss < best_loss {
                best_vertex_index = j;
                best_loss = loss;
            }
        }
        edges.insert((i, best_vertex_index));
    }
}

// ──────────────────────────────────────────────────────────────────────
// Path generation (mirrored from path.rs)
// ──────────────────────────────────────────────────────────────────────

fn generate_poisson_points(radius: f32, region_size: Vec2, rejection_iter: usize, seed: u64) -> Vec<Vec2> {
    let cell_size = radius / f32::sqrt(2.0);
    let grid_size_x = (region_size.x / cell_size).floor() as usize + 1;
    let grid_size_y = (region_size.y / cell_size).floor() as usize + 1;
    let mut grid: Vec<Vec<i32>> = vec![vec![-1; grid_size_x]; grid_size_y];

    let mut points: Vec<Vec2> = vec![region_size / 2.0];
    let mut spawn_points: Vec<Vec2> = vec![region_size / 2.0];

    let mut rng = Xoshiro256PlusPlus::seed_from_u64(seed);

    while !spawn_points.is_empty() {
        let spawn_index = rng.gen_range(0..spawn_points.len());
        let spawn_center = spawn_points[spawn_index];

        let mut candidate_accepted = false;
        for _ in 0..rejection_iter {
            let angle: f32 = rng.gen_range(0.0..2.0 * PI);
            let dir = Vec2::new(angle.sin(), angle.cos());
            let candidate = spawn_center + dir * rng.gen_range(radius..2.0 * radius);

            if !is_valid(candidate, region_size, cell_size, radius, &points, &grid) {
                continue;
            }

            points.push(candidate);
            spawn_points.push(candidate);
            grid[(candidate.y / cell_size).floor() as usize]
                [(candidate.x / cell_size).floor() as usize] = points.len() as i32 - 1;
            candidate_accepted = true;
            break;
        }

        if !candidate_accepted {
            spawn_points.remove(spawn_index);
        }
    }

    points.iter_mut().map(|x| *x - region_size / 2.0).collect()
}

fn is_valid(
    candidate: Vec2,
    region_size: Vec2,
    cell_size: f32,
    radius: f32,
    points: &[Vec2],
    grid: &[Vec<i32>],
) -> bool {
    if candidate.x < 0.0 || candidate.x >= region_size.x || candidate.y < 0.0 || candidate.y >= region_size.y {
        return false;
    }

    let cell_x = (candidate.x / cell_size) as i32;
    let cell_y = (candidate.y / cell_size) as i32;

    let search_start_x = (cell_x - 2).max(0) as usize;
    let search_end_x = (cell_x + 2).min(grid[0].len() as i32) as usize;
    let search_start_y = (cell_y - 2).max(0) as usize;
    let search_end_y = (cell_y + 2).min(grid.len() as i32) as usize;

    for x in search_start_x..search_end_x {
        for y in search_start_y..search_end_y {
            let point_index = grid[y][x];
            if point_index != -1 {
                let distance = (candidate - points[point_index.max(0) as usize]).length_squared();
                if distance < radius.powi(2) {
                    return false;
                }
            }
        }
    }
    true
}

fn compute_path_points(p1: Vec2, p2: Vec2, c1: Vec2, c2: Vec2, sample_size: usize) -> Vec<IVec2> {
    fn curve(p1: Vec2, p2: Vec2, c1: Vec2, c2: Vec2, t: f32) -> Vec2 {
        (1.0 - t).powi(3) * p1
            + 3.0 * t * (1.0 - t).powi(2) * c1
            + 3.0 * t.powi(2) * (1.0 - t) * c2
            + t.powi(3) * p2
    }

    let mut points = Vec::new();
    for i in 0..sample_size {
        let t = i as f32 / sample_size as f32;
        let pos = curve(p1, p2, c1, c2, t);
        points.push(IVec2::new(pos.x as i32, pos.y as i32));
    }
    points
}

fn generate_bezier_points(rng: &mut Xoshiro256PlusPlus, p1: Vec2, p2: Vec2) -> (Vec2, Vec2) {
    let min_p = Vec2::new(p1.x.min(p2.x), p1.y.min(p2.y));
    let max_p = Vec2::new(p1.x.max(p2.x), p1.y.max(p2.y));
    let c1 = Vec2::new(rng.gen_range(min_p.x..max_p.x), rng.gen_range(min_p.y..max_p.y));
    let c2 = Vec2::new(rng.gen_range(min_p.x..max_p.x), rng.gen_range(min_p.y..max_p.y));
    (c1, c2)
}

fn fill_path_point(bitmap: &mut BitMap, v: IVec2) {
    let w = Vec2::new(v.x as f32, v.y as f32);

    let noise = simplex_noise_2d_seeded(w * NOISE_ZOOM, bitmap.seed);
    let secondary_noise = simplex_noise_2d_seeded(w * NOISE_ZOOM, bitmap.seed + 1.0);

    let min_radius = 1;
    let max_radius = min_radius + 1;
    let min_radius_grass = max_radius + 1;
    let max_radius_grass = min_radius_grass + 3;

    let radius = (min_radius as f32
        + 0.25 * (noise + secondary_noise + 2.0) * (max_radius - min_radius) as f32)
        as i32;
    let sqrt_radius = radius.pow(2);
    let radius_grass = (min_radius_grass as f32
        + 0.25 * (noise + secondary_noise + 2.0) * (max_radius_grass - min_radius_grass) as f32)
        as i32;
    let sqrt_radius_grass = radius_grass.pow(2);

    for x in -radius_grass..=radius_grass {
        for y in -radius_grass..=radius_grass {
            let offset = IVec2::new(x, y);
            let dis = offset.length_squared();
            if dis < sqrt_radius {
                bitmap.set_type_flag(v + offset, PATH_TYPE_MASK);
            } else if dis < sqrt_radius_grass && !bitmap.get_type_flag(v + offset, PATH_TYPE_MASK) {
                bitmap.set_type_flag(v + offset, GRASS_TYPE_MASK);
            }
        }
    }
}

fn fill_path_points(bitmap: &mut BitMap, points: Vec<IVec2>) {
    for v in points {
        fill_path_point(bitmap, v);
    }
}

fn generate_path(bitmap: &mut BitMap) {
    let vertices = generate_poisson_points(
        DISK_RADIUS,
        REGION_SIZE,
        POISSON_REJECTION_ITER,
        bitmap.seed as u64,
    );
    bitmap.vertices = vertices.clone();

    let mut edges = kruskals_edges(&vertices);
    connect_outer_vertices(&vertices, &mut edges);
    bitmap.edges = edges.clone();
    let mut edges: Vec<(usize, usize)> = edges.into_iter().collect();
    edges.sort();

    let mut rng = Xoshiro256PlusPlus::seed_from_u64(bitmap.seed as u64);
    for (u, v) in edges {
        let (p1, p2) = (vertices[u], vertices[v]);
        let (c1, c2) = generate_bezier_points(&mut rng, p1, p2);
        let points = compute_path_points(p1, p2, c1, c2, SAMPLE_RATE);
        fill_path_points(bitmap, points);
    }
}

fn fill_player_starting_position(bitmap: &mut BitMap) {
    for x in -START_FILL_RADIUS..=START_FILL_RADIUS {
        for y in -START_FILL_RADIUS..=START_FILL_RADIUS {
            let v = IVec2::new(x, y);
            if v.length_squared() <= START_FILL_RADIUS.pow(2) {
                bitmap.set_type_flag(v, GRASS_TYPE_MASK);
            }
        }
    }
}

// ──────────────────────────────────────────────────────────────────────
// Tiled JSON export types
// ──────────────────────────────────────────────────────────────────────

#[derive(Serialize)]
struct TiledMap {
    width: u32,
    height: u32,
    tilewidth: u32,
    tileheight: u32,
    infinite: bool,
    layers: Vec<serde_json::Value>,
    tilesets: Vec<TilesetRef>,
    nextlayerid: u32,
    nextobjectid: u32,
    orientation: String,
    renderorder: String,
    tiledversion: String,
    #[serde(rename = "type")]
    map_type: String,
    version: String,
}

#[derive(Serialize)]
struct TilesetRef {
    firstgid: u32,
    source: String,
}

#[derive(Serialize)]
struct TiledObject {
    id: u32,
    name: String,
    #[serde(rename = "type")]
    obj_type: String,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

#[derive(Serialize)]
struct TiledTileset {
    columns: u32,
    image: String,
    imageheight: u32,
    imagewidth: u32,
    margin: u32,
    name: String,
    spacing: u32,
    tilecount: u32,
    tileheight: u32,
    tilewidth: u32,
    #[serde(rename = "type")]
    ts_type: String,
    version: String,
    tiledversion: String,
    tiles: Vec<serde_json::Value>,
}

// ──────────────────────────────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────────────────────────────

fn main() {
    println!("map-bootstrapper: generating {}x{} tile map centered on origin", MAP_WIDTH, MAP_HEIGHT);

    let origin_x = -(MAP_WIDTH as i32 / 2);
    let origin_y = -(MAP_HEIGHT as i32 / 2);

    let mut bitmap = BitMap::new(origin_x, origin_y, MAP_WIDTH as usize, MAP_HEIGHT as usize);

    // Step 1: Fill player starting position (grass circle around origin)
    println!("  -> filling player starting position...");
    fill_player_starting_position(&mut bitmap);

    // Step 2: Generate path network (Poisson → MST → Bezier → fill)
    println!("  -> generating path network...");
    generate_path(&mut bitmap);

    // Step 3: Classify all tiles (water/grass/path) and assign tile indices
    println!("  -> classifying tiles...");
    // We also need to run the gen for edge tiles that neighbor our map bounds
    // (the bitmask checks neighbors, so we need one extra row/col)
    let margin = 1;
    for y in (origin_y - margin)..=(origin_y + MAP_HEIGHT as i32 + margin) {
        for x in (origin_x - margin)..=(origin_x + MAP_WIDTH as i32 + margin) {
            bitmap.get_tile_index(IVec2::new(x, y));
        }
    }

    // Step 4: Build tile layer data
    println!("  -> building tile layer data...");
    let mut tile_data: Vec<u32> = Vec::with_capacity((MAP_WIDTH * MAP_HEIGHT) as usize);
    // Tiled rows run top-down while game y runs up, so emit rows from the top.
    for y in (0..MAP_HEIGHT).rev() {
        for x in 0..MAP_WIDTH {
            let v = IVec2::new(origin_x + x as i32, origin_y + y as i32);
            let index = bitmap.get_tile_index(v);
            // Tiled GID is 1-based; 0 = empty
            if index == INVALID_TILE {
                tile_data.push(0);
            } else {
                tile_data.push(index as u32 + 1);
            }
        }
    }

    // Step 5: Build object layers (flora, NPCs, spawn point)
    // For the bootstrap, we place placeholder objects at known positions
    // based on the procedural gen output.
    // Flora positions come from the same Poisson distribution used for paths.
    let flora_objects = generate_flora_objects(&bitmap);
    let npc_objects = generate_npc_objects(&bitmap);
    let spawn_objects = generate_spawn_objects();

    // Step 6: Build layers
    let ground_layer = serde_json::json!({
        "data": tile_data,
        "height": MAP_HEIGHT,
        "id": 1,
        "name": "Ground",
        "opacity": 1.0,
        "type": "tilelayer",
        "visible": true,
        "width": MAP_WIDTH,
        "x": 0,
        "y": 0
    });

    let flora_layer = serde_json::json!({
        "draworder": "topdown",
        "id": 2,
        "name": "Flora",
        "objects": flora_objects,
        "opacity": 1.0,
        "type": "objectgroup",
        "visible": true,
        "x": 0,
        "y": 0
    });

    let npc_layer = serde_json::json!({
        "draworder": "topdown",
        "id": 3,
        "name": "NPCs",
        "objects": npc_objects,
        "opacity": 1.0,
        "type": "objectgroup",
        "visible": true,
        "x": 0,
        "y": 0
    });

    let spawn_layer = serde_json::json!({
        "draworder": "topdown",
        "id": 4,
        "name": "Spawn",
        "objects": spawn_objects,
        "opacity": 1.0,
        "type": "objectgroup",
        "visible": true,
        "x": 0,
        "y": 0
    });

    // Step 7: Build the TMJ map
    let tiled_map = TiledMap {
        width: MAP_WIDTH,
        height: MAP_HEIGHT,
        tilewidth: 16,
        tileheight: 16,
        infinite: false,
        layers: vec![ground_layer, flora_layer, npc_layer, spawn_layer],
        tilesets: vec![TilesetRef {
            firstgid: 1,
            source: "../library/tilesets/forest/tileset.tsj".to_string(),
        }],
        nextlayerid: 5,
        nextobjectid: 100,
        orientation: "orthogonal".to_string(),
        renderorder: "right-down".to_string(),
        tiledversion: "1.11".to_string(),
        map_type: "map".to_string(),
        version: "1.11".to_string(),
    };

    // Step 8: Build the TSJ tileset
    let tileset = TiledTileset {
        columns: 16,
        image: "tileset.png".to_string(),
        imageheight: 256,
        imagewidth: 256,
        margin: 0,
        name: "tileset".to_string(),
        spacing: 0,
        tilecount: 256,
        tileheight: 16,
        tilewidth: 16,
        ts_type: "tileset".to_string(),
        version: "1.11".to_string(),
        tiledversion: "1.11".to_string(),
        tiles: Vec::new(), // No collision shapes in the initial bootstrap
    };

    // Step 9: Write files
    let maps_dir = Path::new("assets/maps");
    std::fs::create_dir_all(maps_dir).expect("Failed to create assets/maps directory");
    let assets_dir = Path::new("assets/library/tilesets/forest");
    std::fs::create_dir_all(assets_dir).expect("Failed to create tileset directory");

    let tmj_path = maps_dir.join("forest.tmj");
    let tmj_json = serde_json::to_string_pretty(&tiled_map).expect("Failed to serialize TMJ");
    std::fs::write(&tmj_path, &tmj_json).expect("Failed to write TMJ");
    println!("  -> wrote {}", tmj_path.display());

    let tsj_path = assets_dir.join("tileset.tsj");
    let tsj_json = serde_json::to_string_pretty(&tileset).expect("Failed to serialize TSJ");
    std::fs::write(&tsj_path, &tsj_json).expect("Failed to write TSJ");
    println!("  -> wrote {}", tsj_path.display());

    println!("Done! Map generated at {} ({}x{} tiles)", tmj_path.display(), MAP_WIDTH, MAP_HEIGHT);
}

// ──────────────────────────────────────────────────────────────────────
// Object layer generators
// ──────────────────────────────────────────────────────────────────────

fn generate_flora_objects(bitmap: &BitMap) -> Vec<serde_json::Value> {
    // Run Poisson sampling to find flora positions.
    // We use the same seed as the BitMap, but we need to generate within
    // the map bounds and use the same RNG state for reproducibility.
    // For the bootstrap, we generate clustered positions around the map center.
    let mut objects = Vec::new();
    let mut rng = Xoshiro256PlusPlus::seed_from_u64(bitmap.seed as u64 + 100);

    // Generate some trees, bushes, and rocks scattered around grass areas
    let origin_x = -(MAP_WIDTH as i32 / 2);
    let origin_y = -(MAP_HEIGHT as i32 / 2);
    let center = IVec2::new(0, 0);

    // Place trees (large, spaced out) across the full map
    let map_center = (MAP_WIDTH * 16 / 2) as f32;
    let tree_positions = generate_poisson_points(64.0, Vec2::new(MAP_WIDTH as f32 * 16.0, MAP_HEIGHT as f32 * 16.0), 20, bitmap.seed as u64 + 200);
    for (i, pos) in tree_positions.iter().enumerate().take(25) {
        // Shift from centered (0,0) to Tiled coordinates (0, 1600)
        let world_x = pos.x + map_center;
        let world_y = pos.y + map_center;
        if world_x >= 0.0 && world_x < (MAP_WIDTH * 16) as f32
            && world_y >= 0.0 && world_y < (MAP_HEIGHT * 16) as f32
        {
            objects.push(serde_json::json!({
                "id": i as u32 + 1,
                "name": format!("Tree{}", i + 1),
                "type": "tree",
                "x": world_x as f64,
                "y": world_y as f64,
                "width": 16.0,
                "height": 16.0
            }));
        }
    }

    // Place bushes (smaller, more dense) across the full map
    let bush_positions = generate_poisson_points(32.0, Vec2::new(MAP_WIDTH as f32 * 16.0, MAP_HEIGHT as f32 * 16.0), 20, bitmap.seed as u64 + 300);
    for (i, pos) in bush_positions.iter().enumerate().take(60) {
        let world_x = pos.x + map_center;
        let world_y = pos.y + map_center;
        if world_x >= 0.0 && world_x < (MAP_WIDTH * 16) as f32
            && world_y >= 0.0 && world_y < (MAP_HEIGHT * 16) as f32
        {
            let bush_type = if i % 2 == 0 { "bush1" } else { "bush2" };
            objects.push(serde_json::json!({
                "id": (100 + i) as u32,
                "name": format!("Bush{}", i + 1),
                "type": bush_type,
                "x": world_x as f64,
                "y": world_y as f64,
                "width": 16.0,
                "height": 16.0
            }));
        }
    }

    // Place rocks (small, clustered) across the full map
    for i in 0..40 {
        let x: f32 = rng.gen_range(0.0..(MAP_WIDTH * 16) as f32);
        let y: f32 = rng.gen_range(0.0..(MAP_HEIGHT * 16) as f32);
        objects.push(serde_json::json!({
            "id": (200 + i) as u32,
            "name": format!("Rock{}", i + 1),
            "type": "rock",
            "x": x as f64,
            "y": y as f64,
            "width": 8.0,
            "height": 8.0
        }));
    }

    objects
}

fn generate_npc_objects(_bitmap: &BitMap) -> Vec<serde_json::Value> {
    // NPC positions in Tiled coordinates (top-left origin, y-down)
    // Game coordinates are converted to Tiled coordinates:
    //   tiled_x = game_x + 800,  tiled_y = -game_y + 800
    // Game positions: Eleonore at (400, 400), Jotem at (-400, 400),
    // Isabelle at (400, -400), IonasAntonius at (-400, -400)
    let center = (MAP_WIDTH * 16 / 2) as f64;
    vec![
        serde_json::json!({
            "id": 1,
            "name": "Eleonore",
            "type": "",
            "x": center + 400.0,
            "y": center - 400.0,
            "width": 16.0,
            "height": 16.0
        }),
        serde_json::json!({
            "id": 2,
            "name": "Jotem",
            "type": "",
            "x": center - 400.0,
            "y": center - 400.0,
            "width": 16.0,
            "height": 16.0
        }),
        serde_json::json!({
            "id": 3,
            "name": "Isabelle",
            "type": "",
            "x": center + 400.0,
            "y": center + 400.0,
            "width": 16.0,
            "height": 16.0
        }),
        serde_json::json!({
            "id": 4,
            "name": "IonasAntonius",
            "type": "",
            "x": center - 400.0,
            "y": center + 400.0,
            "width": 16.0,
            "height": 16.0
        }),
    ]
}

fn generate_spawn_objects() -> Vec<serde_json::Value> {
    // Spawn point at the center of the map
    // Tiled coordinates: center of 100x100 tile map (each tile 16px)
    let center = (MAP_WIDTH * 16 / 2) as f64;
    vec![
        serde_json::json!({
            "id": 1,
            "name": "SpawnPoint",
            "type": "",
            "x": center,
            "y": center,
            "width": 16.0,
            "height": 16.0
        }),
    ]
}