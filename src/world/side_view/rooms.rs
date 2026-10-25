//! The rooms of a side-view map and the doors between them.
//!
//! A map holds several rooms as strips (`Rooms` rectangles), each with a `Floor`
//! polyline inside it. `Portals` are points on a floor that lead to another portal, named
//! by their `to` property: a door, the stairs. A walk to a point in another room goes
//! through the portals in between.

use std::collections::VecDeque;

use bevy::prelude::*;

use crate::world::map::tiled_map::TiledMap;

/// One room: what the camera may show and where its floor is.
#[derive(Clone, Debug, PartialEq)]
pub struct Room {
    pub name: String,
    /// What the camera may show, in game space
    pub bounds: Rect,
    /// The y of a character's transform on this floor (the feet line plus the feet offset)
    pub stand_y: f32,
    pub min_x: f32,
    pub max_x: f32,
}

/// A way from one room into another, standing at `pos`.
#[derive(Clone, Debug, PartialEq)]
pub struct Portal {
    pub name: String,
    pub room: usize,
    /// Transform-space position of a character standing at the portal
    pub pos: Vec2,
    /// The portal it leads to
    pub to: usize,
}

/// A walk through rooms: the points to walk to, and after which of them the walker
/// steps through a portal to the next point.
#[derive(Debug, Default, PartialEq)]
pub struct Route {
    pub points: Vec<Vec2>,
    pub teleports: Vec<usize>,
}

#[derive(Resource, Clone, Debug, Default)]
pub struct SideRooms {
    pub rooms: Vec<Room>,
    pub portals: Vec<Portal>,
}

impl SideRooms {
    pub fn from_map(map: &TiledMap) -> Self {
        let feet = map.feet_offset();
        let floors: Vec<(Vec2, Vec2)> = map
            .object_layer("Floor")
            .iter()
            .filter(|obj| obj.points.len() >= 2)
            .map(|obj| {
                let xs = obj.points.iter().map(|p| p.x);
                let min = xs.clone().fold(f32::MAX, f32::min);
                let max = xs.fold(f32::MIN, f32::max);
                (
                    map.tiled_to_game(min, obj.points[0].y),
                    map.tiled_to_game(max, obj.points[0].y),
                )
            })
            .collect();

        let mut room_objects: Vec<(String, Rect)> = map
            .object_layer("Rooms")
            .iter()
            .map(|obj| {
                (
                    obj.name.clone(),
                    Rect::from_corners(
                        map.tiled_to_game(obj.x, obj.y),
                        map.tiled_to_game(obj.x + obj.width, obj.y + obj.height),
                    ),
                )
            })
            .collect();
        // A map without rooms is one room.
        if room_objects.is_empty() {
            room_objects.push(("Room".to_string(), map.world_bounds()));
        }

        let rooms = room_objects
            .into_iter()
            .map(|(name, bounds)| {
                let floor = floors
                    .iter()
                    .find(|(start, _)| bounds.contains(*start))
                    .copied();
                let (start, end) = floor.unwrap_or_else(|| {
                    warn!("Room '{name}' has no Floor polyline, using its middle");
                    let mid = bounds.center().y;
                    (Vec2::new(bounds.min.x, mid), Vec2::new(bounds.max.x, mid))
                });
                Room {
                    name,
                    bounds,
                    stand_y: start.y + feet,
                    min_x: start.x,
                    max_x: end.x,
                }
            })
            .collect::<Vec<_>>();

        let mut sides = Self {
            rooms,
            portals: Vec::new(),
        };
        // Portals in a room first, then each one's `to` resolved among them.
        let mut targets = Vec::new();
        for obj in map.object_layer("Portals") {
            let feet_pos = map.tiled_to_game(obj.x, obj.y);
            let Some(room) = sides.room_at(feet_pos) else {
                warn!("Portal '{}' lies in no room, skipping", obj.name);
                continue;
            };
            sides.portals.push(Portal {
                name: obj.name.clone(),
                room,
                pos: Vec2::new(feet_pos.x, sides.rooms[room].stand_y),
                to: 0,
            });
            targets.push(obj.prop_str("to").unwrap_or("").to_string());
        }
        let resolved: Vec<Option<usize>> = targets
            .iter()
            .map(|target| sides.portals.iter().position(|p| p.name == *target))
            .collect();
        for (portal, to) in sides.portals.iter_mut().zip(&resolved) {
            match to {
                Some(to) => portal.to = *to,
                None => warn!("Portal '{}' leads to no known portal", portal.name),
            }
        }
        // A portal that leads nowhere just leads to itself, which no route takes.
        for (i, to) in resolved.iter().enumerate() {
            if to.is_none() {
                sides.portals[i].to = i;
            }
        }
        sides
    }

    /// The room containing `pos`.
    pub fn room_at(&self, pos: Vec2) -> Option<usize> {
        self.rooms.iter().position(|room| room.bounds.contains(pos))
    }

    /// The portals to step through, in order, to get from room `from` to room `to`.
    fn portal_chain(&self, from: usize, to: usize) -> Option<Vec<usize>> {
        let mut came_by: Vec<Option<usize>> = vec![None; self.rooms.len()];
        let mut seen = vec![false; self.rooms.len()];
        let mut queue = VecDeque::from([from]);
        seen[from] = true;
        while let Some(room) = queue.pop_front() {
            if room == to {
                let mut chain = Vec::new();
                let mut at = to;
                while let Some(portal) = came_by[at] {
                    chain.push(portal);
                    at = self.portals[portal].room;
                }
                chain.reverse();
                return Some(chain);
            }
            for (i, portal) in self.portals.iter().enumerate() {
                let next = self.portals[portal.to].room;
                if portal.room == room && !seen[next] {
                    seen[next] = true;
                    came_by[next] = Some(i);
                    queue.push_back(next);
                }
            }
        }
        None
    }

    /// The walk from `start` through `points`, stepping through portals wherever the
    /// next point is in another room. Points in no room, or rooms with no way between
    /// them, are walked to directly.
    pub fn route(&self, start: Vec2, points: &[Vec2]) -> Route {
        let mut route = Route::default();
        let mut room = self.room_at(start);
        for &point in points {
            let target_room = self.room_at(point);
            if let (Some(from), Some(to)) = (room, target_room) {
                for portal in self.portal_chain(from, to).unwrap_or_default() {
                    let portal = &self.portals[portal];
                    route.teleports.push(route.points.len());
                    route.points.push(portal.pos);
                    route.points.push(self.portals[portal.to].pos);
                }
            }
            route.points.push(point);
            room = target_room.or(room);
        }
        route
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn room(name: &str, y: f32) -> Room {
        Room {
            name: name.to_string(),
            bounds: Rect::new(0.0, y, 1000.0, y + 500.0),
            stand_y: y + 100.0,
            min_x: 50.0,
            max_x: 950.0,
        }
    }

    /// Landing (0) with a door into 3B (1) and one into 3A (2); 3B and 3A don't connect.
    fn building() -> SideRooms {
        let portal = |name: &str, room: usize, x: f32, to: usize| Portal {
            name: name.to_string(),
            room,
            pos: Vec2::new(x, [100.0, 600.0, 1100.0][room]),
            to,
        };
        SideRooms {
            rooms: vec![room("Landing", 0.0), room("3B", 500.0), room("3A", 1000.0)],
            portals: vec![
                portal("Landing3B", 0, 300.0, 1),
                portal("Inside3B", 1, 100.0, 0),
                portal("Landing3A", 0, 700.0, 3),
                portal("Inside3A", 2, 800.0, 2),
            ],
        }
    }

    #[test]
    fn a_walk_inside_one_room_goes_straight() {
        let route = building().route(Vec2::new(100.0, 100.0), &[Vec2::new(400.0, 100.0)]);
        assert_eq!(route.points, vec![Vec2::new(400.0, 100.0)]);
        assert!(route.teleports.is_empty());
    }

    #[test]
    fn a_walk_into_another_room_goes_through_its_door() {
        let target = Vec2::new(500.0, 600.0);
        let route = building().route(Vec2::new(100.0, 100.0), &[target]);
        assert_eq!(
            route.points,
            vec![Vec2::new(300.0, 100.0), Vec2::new(100.0, 600.0), target]
        );
        assert_eq!(route.teleports, vec![0]);
    }

    #[test]
    fn a_walk_between_flats_crosses_the_landing() {
        let target = Vec2::new(200.0, 1100.0);
        let route = building().route(Vec2::new(400.0, 600.0), &[target]);
        assert_eq!(
            route.points,
            vec![
                Vec2::new(100.0, 600.0),
                Vec2::new(300.0, 100.0),
                Vec2::new(700.0, 100.0),
                Vec2::new(800.0, 1100.0),
                target,
            ]
        );
        assert_eq!(route.teleports, vec![0, 2]);
    }

    #[test]
    fn rooms_without_a_way_between_them_walk_directly() {
        let mut rooms = building();
        rooms.portals.clear();
        let target = Vec2::new(200.0, 1100.0);
        let route = rooms.route(Vec2::new(400.0, 600.0), &[target]);
        assert_eq!(route.points, vec![target]);
    }
}
