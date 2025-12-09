from base_entity import Entity, EntityType, Coord, Property
from enum import Enum
from base_rule import RuleManager, Rule, NounIsNoun, NounIsProperty, Token
from util import Deque
import json
import hashlib
import threading

# Length (in hex chars) of the state hash returned by _get_state_hash.
# Default 16 hex chars -> 64 bits. Increase if collision risk is a concern.
STATE_HASH_HEX_LENGTH = 16

class GameOutcome(Enum):
    Continue = 0
    Win = 1
    Defeat = 2
    Still = 3
    Quit = 4

    def __str__(self):
        return self.name

class Action(Enum):
    wait, undo, quit, restart = ' ', 'z', 'q', 'r'
    up, down, left, right = 'w', 's', 'a', 'd'

    @classmethod
    def from_char(cls, char):
        try:
            return cls(char)
        except ValueError:
            raise ValueError(f'Invalid action: {char}')
    
    def sort_entities(self, entities):
        KEYMAP = {
            'up': lambda e: -e.get_y(),
            'down': Entity.get_y,
            'left': Entity.get_x,
            'right': lambda e: -e.get_x(),
        }
        key = KEYMAP.get(self.name, lambda e: 0)
        return sorted(entities, key = key)

    
    def is_move(self):
        return self in [Action.up, Action.down, Action.left, Action.right]
    
    def is_special(self):
        return self in [Action.wait, Action.undo, Action.quit, Action.restart]
    
    def get_neighbor_coord(self, coord):
        if self.is_special() or not coord:
            return coord
        return getattr(coord, self.name)
    
    def get_neighbor_tile(self, item, gridmap=None):
        gridmap = gridmap or item.gridmap
        if self.is_special():
            return gridmap.get_tile(item.get_coord())
        coord = self.get_neighbor_coord(item.get_coord())
        return gridmap.get_tile(coord)
    
    def reverse(self):
        if self.is_special():
            return self
        return {
            Action.up: Action.down,
            Action.down: Action.up,
            Action.left: Action.right,
            Action.right: Action.left,
        }[self]
    
    def __str__(self):
        return self.value
    
    def __repr__(self):
        return self.value

class FakeEmpty(Entity):
    def __init__(self, coord):
        super().__init__('.', coord, None, ['Empty'])

class FakeBoundary(Entity):
    def __init__(self, coord):
        super().__init__('#', coord, -1, ['Stop'])
    

class Tile:
    def __init__(self, coord, gridmap,  entities=None):

        self.gridmap, self.community = gridmap, None
        self.size = (gridmap.width, gridmap.height)
        self.coord = Coord.from_tuple(coord, self.size)
        if self.coord.bound:
            self.entities = [FakeBoundary(self.coord)]
        else:
            self.entities = entities or [FakeEmpty(self.coord)]
        for entity in self.entities:
            entity.tile = self
    
    def get_coord(self):
        return self.coord

    @property
    def prop(self):
        return Property.union([entity.get_prop() for entity in self.entities])

    @property
    def token(self):
        for entity in self.entities:
            if entity.is_text():
                return Token(entity.get_entity_id(), self.coord)
        return Token('', self.coord)

    def get_prop(self):
        return self.prop
    
    def get_prop_set(self):
        return self.prop._props
    
    def get_prop_one_hot(self):
        return [entity.get_prop_one_hot() for entity in self.get_all_entities()]

    def get_sim(self, tile, method='pair', id_weight=0.4):
        a = self.get_all_entities()
        b = tile.get_all_entities()
        if method == 'pair':
            total = 0
            for ent_a in a:
                for ent_b in b:
                    total += ent_a.cal_sim(ent_b, id_weight=id_weight)
            return total / (len(a) * len(b))

    def has_prop(self, prop):
        return prop in self.prop
    
    def add_entity(self, entity):
        assert isinstance(entity, Entity), 'entity must be an Entity'
        # remove any FakeEmpty placeholders when adding a real entity
        self.entities = [e for e in self.entities if not isinstance(e, FakeEmpty)]
        self.entities.append(entity)
        # ensure the gridmap-wide entities list contains this entity
        if entity not in self.gridmap.entities:
            self.gridmap.entities.append(entity)
        entity.tile = self
    
    def remove_entity(self, entity):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be an Entity'
        self.entities.remove(entity)
        # remove from gridmap entity list if present (FakeEmpty may not be tracked there)
        if entity in self.gridmap.entities:
            self.gridmap.entities.remove(entity)
        entity.tile, entity.coord = None, None
        # if no non-fake entities remain, ensure a FakeEmpty placeholder exists
        if not any(not isinstance(e, FakeEmpty) for e in self.entities):
            entity = FakeEmpty(self.coord)
            entity.tile = self
            self.entities = [entity]
    
    def clear_entities(self):
        for entity in self.get_all_entities():
            self.remove_entity(entity)

    def __len__(self):
        return len(self.entities)
    
    def equal_by_prop(self, other):
        assert isinstance(other, Tile), 'other must be a Block'
        return self.prop.get() == other.prop.get()

    def get_full(self):
        return '&'.join(sorted([e.get_identity() for e in self.get_all_entities()]))
    
    def equal_by_entity(self, other):
        return self.get_full() == other.get_full()
    
    def __eq__(self, other):
        return self.equal_by_prop(other)
    
    def get_all_entities(self):
        return sorted(self.entities, key = lambda e: (e.global_id))

    def get_first_entity(self):
        if len(self.entities) > 0:
            return self.entities[0]

    def get_example_entity_id(self):
        # consider only non-fake entities for example id
        nonfake = [e for e in self.entities if not isinstance(e, FakeEmpty)]
        if len(nonfake) == 0:
            return 'o'
        if len(nonfake) >= 2:
            return '?'
        return nonfake[0].get_entity_id()
    
    def get_token(self):
        return self.token
    
    def is_token(self):
        return self.token.is_token()

    def check_collisions(self):
        prop = self.get_prop()
        if len(prop) <= 1:
            return GameOutcome.Continue
        entities = self.get_all_entities()

        if 'DEFEAT' in prop:
            [self.remove_entity(e) for e in entities if e.has_prop('YOU')]
        
        if 'SINK' in prop:
            [self.remove_entity(e) for e in entities]
        
        if 'HOT' in prop and 'MELT' in prop:
            [self.remove_entity(e) for e in entities if e.has_prop('MELT')]

        if 'WIN' in prop and 'YOU' in prop:
            return GameOutcome.Win
        
        return GameOutcome.Continue
    
    def is_empty(self):
        # A tile is considered empty when it contains no non-fake entities.
        return not any(not isinstance(e, FakeEmpty) for e in self.entities)
    
    def is_token(self):
        return any(entity.is_text() for entity in self.entities)
    
    def is_single(self):
        # Single if exactly one non-fake entity
        nonfake = [e for e in self.entities if not isinstance(e, FakeEmpty)]
        return len(nonfake) == 1
    
    def is_boundary(self):
        return self.coord.bound
    
    def is_multi(self):
        return len(self.entities) > 1
    
    def get_description(self, exact = True):
        if self.is_empty():
            return f'@{self.coord}: Empty'
        elif self.is_single():
            return self.get_first_entity().get_description(exact)
        else:
            return f'@{self.coord}: Multi [{self.prop.get_description()}]'

    def __str__(self):
        return self.get_description()
    
    def __repr__(self):
        return self.get_description()
    
class TileDict(dict):
    def __init__(self, gridmap):
        super().__init__()
        self._gridmap = gridmap
    
    def __missing__(self, coord):
        block = Tile(coord, self._gridmap, [])
        block.coord.size = (self._gridmap.width, self._gridmap.height)
        self[coord] = block
        return block
    
class GameEngine:
    def __init__(self, width = 8, height = 6):
        self.id_counter = 0
        self.size = (width, height)
        self.width, self.height = width, height

        self.entities = []
        self.tiles = TileDict(self)
        self.rule_manager = RuleManager(self)
        self.game_history = [(Action.restart, self.quick_save())]
        self.state = GameOutcome.Continue
    
    # ====== 存储读取 ======

    def deep_copy(self):
        return self.__class__.quick_load(self.quick_save())
    
    def update_rules(self):
        self.rule_manager.update_rules()

    def quick_save(self):
        record = ";".join(entity.quick_save() for entity in self.get_all_entities())
        return str(self.width) + ',' + str(self.height) + '|' + record

    @classmethod
    def quick_load(cls, data):
        size, record = data.split('|')
        size = [int(dim) for dim in size.split(',')]
        grid = cls(size[0], size[1])
        for entity_data in record.split(';'):
            entity = Entity.quick_load(entity_data)
            grid.add_entity(entity, assign_id=False)
        grid.update_rules()
        grid.game_history = [(Action.restart, data)]
        return grid
    
    @classmethod
    def from_text(cls, text):
        lines = text.strip().split('\n')
        lines = [''.join(line.split(' ')) for line in lines]
        
        # 计算实际的地图尺寸（忽略空格）
        max_width = max(len(line.strip()) for line in lines)
        height = len(lines)
        grid = cls(max_width, height)
        
        for y, line in enumerate(reversed(lines)):
            # 移除行首尾空格，但保持内部结构
            stripped_line = line.strip()
            for x, char in enumerate(stripped_line):
                if char != '.' and char != ' ':
                    entity = Entity(char.strip(), (x, y))
                    grid.add_entity(entity)
        
        grid.update_rules()
        grid.game_history = [(Action.restart, grid.quick_save())]
        return grid
    
    def save_text(self):
        string = ''
        for y in reversed(range(self.height)):
            for x in range(self.width):
                block = self.get_tile(Coord.from_tuple((x, y)))
                if block.is_empty():
                    string += '.'
                elif block.is_single():
                    string += block.get_example_entity_id()
                else:
                    string += '?'
            string += '\n'
        return string

    # ====== entity 管理 ======
    def add_entity(self, entity, assign_id=True):
        assert isinstance(entity, Entity), 'entity must be an Entity'
        entity.gridmap_init(self)
        self.tiles[entity.get_coord()].add_entity(entity)
        if assign_id:
            entity.global_id = self.id_counter
            self.id_counter += 1

    def remove_entity(self, entity):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be in the gridmap'
        self.tiles[entity.get_coord()].remove_entity(entity)
    
    def move_entity(self, entity, coord):
        self.remove_entity(entity)
        entity.set_coord(coord)
        self.add_entity(entity, assign_id=False)

    # ====== 获取信息 ======
    def get_size(self):
        return self.size
    
    def get_all_entities(self, fast=True):
        if fast:
            return sorted(self.entities, key = lambda e: e.global_id)
        all_entities = []
        for tile in self.tiles.values():
            all_entities.extend(tile.get_all_entities())
        return all_entities

    def get_entities_by_id(self, target):
        target = target.get_entity_id() if isinstance(target, Entity) else target
        return list([entity for entity in self.entities if entity.get_entity_id() == target])
    
    def get_entities_by_prop(self, target, fast=True):
        if isinstance(target, Entity):
            target = target.get_prop()
        return list([entity for entity in self.get_all_entities(fast) if entity.has_prop(target)])
    
    def get_tile(self, coord):
        if coord is None:
            return None
        return self.tiles[Coord.from_tuple(coord, self.size)]
    
    def get_empty_coords(self):
        return {coord for coord, tile in self.tiles.items() if tile.is_empty()}
    
    def get_agent(self):
        return self.get_entities_by_prop('YOU')
        

    def count_agent(self):
        return len(self.get_entities_by_prop('YOU'))

    
    def iter_tiles(self):
        for coord, tile in self.tiles.items():
            if coord:
                yield coord, tile
    
    # ====== 核心地图 ======
    def step(self, action):
        # return (Gridmap, GameOutcom, Dict)
        if action.is_special():
            return getattr(self, '_handle_' + action.name)()
        return self._handle_movement(action)

    def _handle_movement(self, action):
        info = {'event': 'movement', 'push_chain': []}
        outcome = GameOutcome.Continue
        agents = action.sort_entities(self.get_agent())

        for you in agents:
            chain_info = {'chain_list': [], 'finished': False}
            chain_info['finished'] = self._push_chain(you, action, chain_info)
            info['push_chain'].append(chain_info)
        self.rule_manager.update_rules()
        for tile in self.tiles.values():
            if tile.check_collisions() == GameOutcome.Win:
                outcome = GameOutcome.Win

        self.game_history.append((action, self.quick_save()))
        if self.count_agent() == 0:
            outcome = GameOutcome.Defeat
        self.state = outcome
        return self, outcome, info

    def _push_chain(self, pusher, action, chain_info):
        
        pusher = [pusher] if isinstance(pusher, Entity) else pusher
        next_tile = action.get_neighbor_tile(pusher[0], self)

        # # 1：None条件无交互（现在可以删掉了）
        # if next_tile is None:
        #     node = {'pusher': pusher, 'pushed': [], 'blocked_by': 'Boundary'}
        #     chain_info['chain_list'].insert(0, node)
        #     return False

        prop = next_tile.get_prop()
        node = {'pusher': pusher, 'pushed': next_tile.get_all_entities(), 'blocked_by': None}

        # 2：STOP交互（新增了边界）
        if 'STOP' in prop:
            node['blocked_by'] = 'STOP'
            chain_info['chain_list'].insert(0, node)
            return False

        # 3：PUSH交互
        if 'PUSH' in prop or 'TEXT' in prop:
            to_push = [e for e in next_tile.get_all_entities() if e.has_prop('PUSH') or e.has_prop('TEXT')]
            if not self._push_chain(to_push, action, chain_info):
                chain_info['chain_list'].insert(0, node)
                return False

        # 4: OTHER交互
        [self.move_entity(y, next_tile.get_coord()) for y in pusher]
        chain_info['chain_list'].insert(0, node)
        return True

    def _handle_quit(self):
        return self, GameOutcome.Quit, {'event': 'quit', 'push_chain': []}

    def _handle_restart(self):
        initial = self.game_history[0][1]
        self.game_history = [(Action.restart, initial)]
        
        return self.__class__.quick_load(initial), GameOutcome.Continue, {'event': 'restart', 'push_chain': []}
    
    def _handle_wait(self):
        return self, GameOutcome.Continue, {'event': 'wait', 'push_chain': []}
    
    def _handle_undo(self):
        if len(self.game_history) > 1:
            self.game_history.pop()
            record = self.game_history[-1][1]
            last_grid = self.__class__.quick_load(record)
            last_grid.game_history = self.game_history
            return last_grid, GameOutcome.Continue, {'event': 'undo', 'push_chain': []}
        return self, GameOutcome.Continue, {'event': 'undo', 'push_chain': []}

    def __str__(self):
        def spacefill(x):
            if x < 10:
                return ' ' + str(x) + ' '
            if x < 100:
                return ' ' + str(x)
            return str(x)

        string = ''
        for y in reversed(range(self.height)):
            string += spacefill(y) + '|'
            for x in range(self.width):
                block = self.get_tile(Coord.from_tuple((x, y)))
                string += block.get_example_entity_id() + '  '
            string += '\n'
        string += '   ' + ''.join(spacefill(x) for x in range(self.width))
        return string
    
    def __repr__(self):
        return self.__str__()


