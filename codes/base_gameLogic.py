from base_entity import Entity, Material, Coord, Property, Boundary
from enum import Enum
from base_rule import RuleManager, Rule, NounIsNoun, NounIsProperty, Token
from util import Deque
import json
import hashlib
import threading
from util import encoding, decoding
from collections import defaultdict

# Length (in hex chars) of the state hash returned by _get_state_hash.


class GameOutcome(Enum):
    Continue = 0
    Win = 1
    Defeat = 2
    Still = 3
    Quit = 4

    def __str__(self):
        return self.name

class Action(Enum):
    up, down, left, right = 'w', 's', 'a', 'd'
    wait, undo, quit, restart = ' ', 'z', 'q', 'r'
    login, logout = 'I', 'O'

    @classmethod
    def from_char(cls, item) -> 'Action':
        """ 给定文本，识别出对应的 Action 实例 """
        ACTIONCHECK = {'up': 'w', 'down': 's', 'left': 'a', 'right': 'd', 
                   '↑': 'w', '↓': 's', '←': 'a', '→': 'd',
                   'restart': 'r', 'undo': 'z', '↻': 'r', '↶': 'z'}
        if isinstance(item, str):
            string = ACTIONCHECK.get(item.lower(), item)
            return cls(string)
        return item

    def is_move(self):
        return self in [Action.up, Action.down, Action.left, Action.right]
    
    def is_special(self):
        return self in [Action.wait, Action.undo, Action.quit, Action.restart]
    def is_undo(self): return self == Action.undo
    def is_restart(self): return self == Action.restart
    def is_quit(self): return self == Action.quit

    def sort_entities(self, entities):
        KEYMAP = {Action.up: lambda e: -e.get_y(), Action.down: Entity.get_y,
                  Action.left: Entity.get_x, Action.right: lambda e: -e.get_x()}
        return sorted(entities, key = KEYMAP[self]) if self.is_move() else entities
    
    def reverse(self):
        REVERSE = {Action.up: Action.down, Action.down: Action.up, 
                   Action.left: Action.right, Action.right: Action.left}    
        return REVERSE[self] if self.is_move() else self
    
    def get_neighbor_coord(self, coord):
        if not isinstance(coord, Coord):
            coord = Coord(coord)
        return getattr(coord, self.name) if coord and self.is_move() else coord
    
    def get_neighbor_tile(self, item, gridmap=None):
        gridmap = gridmap or item.gridmap
        coord = self.get_neighbor_coord(item.get_coord())
        return gridmap.get_tile(coord)
    
    @property
    def offset(self):
        OFFSETS = {
            Action.up: (0, 1),
            Action.down: (0, -1),
            Action.left: (-1, 0),
            Action.right: (1, 0),
        }
        return OFFSETS.get(self, (0, 0))
    def __repr__(self): return self.value


class FakeEmpty(Entity):
    def __init__(self, coord):
        super().__init__('.', coord)

class FakeBoundary(Entity):
    def __init__(self, coord):
        super().__init__('#', coord, -1)


class Tile:
    def __init__(self, coord, gridmap = None,  entities=None):

        self.gridmap = gridmap
        self.size = gridmap.size if gridmap else None
        self.coord = Coord(coord, self.size)

        self.entities = entities or self.initial_entity()
        for entity in self.entities:
            entity.tile = self
        
        self._prop, self._dirty = None, True
    
    def initial_entity(self):
        return [FakeBoundary(self.coord)] if self.coord.bound else []

    # ===== 基本类型判断 ======
    def __len__(self): return len(self.entities)
    def is_empty(self): return len(self.entities) == 0    
    def is_boundary(self): return self.coord.bound
    def is_single(self): return len(self.entities) == 1
    def is_multi(self): return len(self.entities) > 1

    def get_all_entities(self): 
        return self.entities.copy()
    
    def get_full_entities(self):  # 延迟处理空的
        if self.is_empty():
            return [FakeEmpty(self.coord)]
        return self.get_all_entities()
    
    def get_first_entity(self):
        return self.get_full_entities()[0]
    
    # ====== 修改内容 ======
    def mark_dirty(self): self._dirty = True
    def add_tile_entity(self, entity):
        assert isinstance(entity, Entity), 'entity must be an Entity'
        
        self.entities.append(entity)
        entity.tile, entity.coord = self, self.coord
        
        if self.gridmap is not None:
            self.gridmap.entities.append(entity)
            entity.gridmap = self.gridmap

        self._dirty = True
        if 'TEXT' in entity.get_prop():
            self.gridmap.mark_dirty('rules')
        self.gridmap.mark_dirty('entity_id')
    

    def remove_tile_entity(self, entity):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be an Entity'
        
        self.entities.remove(entity)
        entity.tile, entity.coord = None, None

        if self.gridmap is not None:
            self.gridmap.entities.remove(entity)
            entity.gridmap = None

        self._dirty = True
        if 'TEXT' in entity.get_prop():
            self.gridmap.mark_dirty('rules')
        self.gridmap.mark_dirty('entity_id')
    
    
    def move_tile_entity(self, entity, new_tile):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be an Entity'
        assert isinstance(new_tile, Tile), 'new_tile must be a Tile'

        self.entities.remove(entity)
        self._dirty = True

        new_tile.entities.append(entity)
        new_tile._dirty = True
        entity.tile, entity.coord = new_tile, new_tile.coord

        if 'TEXT' in entity.get_prop():
            self.gridmap.mark_dirty('rules')
        self.gridmap.mark_dirty('image')

    def clear_tile_entities(self):
        for entity in self.get_all_entities():
            self.remove_tile_entity(entity)

    # ====== 获取信息 ======
    def get_coord(self): return self.coord
    def get_prop(self): return self.prop    
    def has_prop(self, prop): return prop in self.prop
        
    @property
    def prop(self):
        if self._dirty:
            self._prop = self.update_prop()
            self._dirty = False
        return self._prop
    
    def update_prop(self):
        return Property.union_props([e.get_prop() for e in self.get_full_entities()])
    
    def get_token(self):
        return ''.join(e.get_entity_id() for e in self.get_all_entities() if e.is_text())
    
    def has_token(self):
        return 'TEXT' in self.prop

    # ====== 核心逻辑 ======
    def check_collisions(self):

        prop = self.get_prop()

        if len(prop) <= 1:
            return
        
        # if 'SINK' in prop:
        #     self.clear_tile_entities()
        #     return

        if 'DEFEAT' in prop:
            for e in self.get_all_entities():
                if e.has_prop('YOU'):
                    self.remove_tile_entity(e)
        
        # if 'HOT' in prop:
        #     for e in self.get_all_entities():
        #         if e.has_prop('MELT'):
        #             self.remove_tile_entity(e)

        if 'WIN' in prop and 'YOU' in prop:
            return GameOutcome.Win

    # ====== 一些可视化 ======

    def quick_save(self, encoding=False):
        idata = [e.quick_save(encoding) for e in self.get_all_entities()]
        return encoding(idata) if encoding else idata

    def get_description(self):

        if self.is_empty():
            return f'@{self.coord}: Empty'
        
        if self.is_single():
            return self.get_first_entity().get_description()

        return f'@{self.coord}: Multi [{self.prop.get_description()}]'

    def __str__(self):
        return self.get_description()
    
    def __repr__(self):
        return self.get_description()


    def get_sim(self, tile, method='pair', id_weight=0.4):
        a = self.get_all_entities()
        b = tile.get_all_entities()
        if method == 'pair':
            total = 0
            for ent_a in a:
                for ent_b in b:
                    total += ent_a.cal_sim(ent_b, id_weight=id_weight)
            return total / (len(a) * len(b))
    
    def equal_by_prop(self, other):
        assert isinstance(other, Tile), 'other must be a Block'
        return self.prop == other.prop

    def get_full(self):
        return '&'.join(sorted([e.get_identity() for e in self.get_all_entities()]))
    
    def equal_by_entity(self, other):
        return self.get_full() == other.get_full()
    
    def __eq__(self, other):
        return self.equal_by_prop(other)
    
    def get_example_entity_id(self):
        # consider only non-fake entities for example id
        if self.is_empty(): return 'o'
        if self.is_multi(): return '?'
        return self.get_first_entity().get_entity_id()

    

class EntityTile(dict):
    def __init__(self, gridmap):
        super().__init__()
        self.gridmap = gridmap
    
    def __missing__(self, coord):
        block = Tile(coord, self.gridmap)
        self[coord] = block
        return block

class EntityProp:
    def __init__(self, entities):
        self._index = defaultdict(list)
        self._source = entities
        self._dirty = True
    
    def items(self):
        self.rebuild()
        return self._index.items()

    def mark_dirty(self):
        self._dirty = True

    def rebuild(self):
        if not self._dirty:
            return 
        self._index.clear()
        for entity in self._source:
            for prop in entity.get_prop_lst():
                self._index[prop].append(entity)
        self._dirty = False
    
    def query(self, prop):
        self.rebuild()
        return self._index.get(prop, []).copy()

class EntityID:
    def __init__(self, entities):
        self._index = defaultdict(list)
        self._source = entities
        self._dirty = True
    
    def items(self):
        self.rebuild()
        return self._index.items()
    
    def mark_dirty(self):
        self._dirty = True
    
    def rebuild(self):
        if not self._dirty:
            return 
        self._index.clear()
        for entity in self._source:
            self._index[entity.get_entity_id()].append(entity)
        self._dirty = False
    
    def query(self, entity_id):
        self.rebuild()
        return self._index.get(entity_id, []).copy()


class Collector:
    def __init__(self, width = 8, height = 6):

        self.id_counter = 0
        self.size, self.width, self.height = (width, height), width, height
        self.entities = []
        self.entity_prop = EntityProp(self.entities)
        self.entity_id = EntityID(self.entities)
        self.entity_coord = EntityTile(self)
        self.rule_manager = RuleManager(self)
        self.image, self._image_dirty = None, False
        self.mark_dirty('all')
    
    def mark_dirty(self, type='all'):
        if type in ['all', 'entity_prop']:
            self.entity_prop.mark_dirty()
        elif type in ['all', 'entity_id']:
            self.entity_id.mark_dirty()
            self.entity_prop.mark_dirty()
        if type in ['all', 'rules']:
            self.rule_manager.mark_dirty()
        self._image_dirty = True

    # ====== 规则管理 ======
    def update_rules(self):
        self.rule_manager.update_all_rules()
    
    def get_rules(self):
        return self.rule_manager.get_all_rules()
    
    def get_ruler(self, manager_name = None):
        if manager_name is None:
            return self.rule_manager.manager
        return self.rule_manager.manager.get(manager_name, None)

    # ====== 基础查询 ======
    def get_size(self): return self.size
    def get_outcome(self): return self.state.name
    
    def get_all_entities(self):
        return self.entities.copy()

    def get_full_entities(self):
        full_e = [e for tile in self.entity_coord.values() for e in tile.get_full_entities()]
        return sorted(full_e, key = lambda e: e.global_id)
    
    def get_tile(self, coord):
        if isinstance(coord, Coord):
            return self.entity_coord[coord]
        return self.entity_coord.get(Coord(coord, self.size))
    
    def get_entity_by_global_id(self, global_id):
        for entity in self.entities:
            if entity.global_id == global_id:
                return entity

    def get_entities_by_id(self, entity_id):
        return self.entity_id.query(entity_id)
    
    def get_entities_by_prop(self, property):
        return self.entity_prop.query(property)
        
    def get_empty_coords(self):
        return {coord for coord, tile in self.entity_coord.items() if tile.is_empty()}
    
    def get_agent(self): return self.get_entities_by_prop('YOU')
    def count_agent(self): return len(self.get_entities_by_prop('YOU'))

    def iter_tiles(self):
        for coord, tile in self.entity_coord.items():
            if coord: yield coord, tile
    
    # ====== entity 管理 ======
    def add_entity(self, entity):
        assert isinstance(entity, Entity), 'entity must be an Entity'

        entity.global_id = self.id_counter
        self.id_counter += 1
        
        self.entity_coord[entity.get_coord()].add_tile_entity(entity)

    def fast_add_entity(self, entity):

        self.entities.append(entity)
        tile = self.get_tile(entity.get_coord())
        tile.entities.append(entity)
        entity.tile = tile
        entity.gridmap = self

    def remove_entity(self, entity):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be in the gridmap'
        entity.tile.remove_tile_entity(entity)

    
    def move_entity(self, entity, coord):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be in the gridmap'
        old_coord, new_coord = entity.get_coord(), Coord(coord, self.size)
        if old_coord == new_coord:
            return 
        entity.tile.move_tile_entity(entity, self.get_tile(new_coord))


    # ====== 极简可视化 ======
    def get_description(self):
        def spacefill(x):
            return format(x, '^3d') if isinstance(x, int) else format(x, '^3')

        string = ''
        # 从上到下每一行
        for y in reversed(range(self.height)):
            string += '\n' + spacefill(y) + '|'

            #从左到右每一列
            for x in range(self.width):
                string += spacefill(self.get_tile((x, y)).get_example_entity_id())

        # 列编号
        string += '\n    ' + ''.join(spacefill(x) for x in range(self.width))
        return string
    
    def __repr__(self):
        return self.get_description()

    # ====== 存档加载 ======
    def quick_save_helper(self):
        if self.image is None or self._image_dirty:
            record = [e.quick_save(False) for e in self.get_all_entities()]
            record.append(self.size)
            self.image = encoding(record)
            self._image_dirty = False
        return self.image

    def quick_save(self):
        return self.quick_save_helper()
    
    @classmethod
    def quick_load(cls, raw_data):
        if isinstance(raw_data, str):
            data = decoding(raw_data)
        else:
            data = raw_data
        size = data.pop()
        grid = cls(size[0], size[1])
        for edata in data:
            grid.fast_add_entity(Entity.quick_load(edata))
        grid.mark_dirty('entity_id')
        grid.update_rules()
        grid.image = raw_data
        grid._image_dirty = False
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
        
        return grid
    
    def save_text(self):
        string = ''
        for y in reversed(range(self.height)):
            for x in range(self.width):
                block = self.get_tile(Coord((x, y), self.size))
                if block.is_empty():
                    string += '.'
                elif block.is_single():
                    string += block.get_example_entity_id()
                else:
                    string += '?'
            string += '\n'
        return string

class GameHistory:
    def __init__(self, init_grid):

        self.cls = init_grid.__class__
        self.history = []
        self.init_grid = init_grid
        self.add_init()
    
    def __len__(self):
        return len(self.history)
    
    def add_init(self):
        self.history.append((Action.login, self.init_grid.quick_save(), self.init_grid.state.name))
    
    def add_record(self, action, grid):
        self.history.append((action, grid.quick_save(), grid.state.name))
        if hasattr(grid, 'describe'):
            grid.describe()
    
    def restart_record(self):
        assert len(self.history) >= 1, 'No history to restart'
        init_record = self.history[0][1]
        self.history.clear()
        self.history.append((Action.restart, init_record))
        grid = self.cls.quick_load(init_record, self)
        return grid
    
    def undo_record(self):
        assert len(self.history) >= 1, 'No history to undo'

        if len(self.history) == 1:
            cur_record = self.history[0][1]
            return self.cls.quick_load(cur_record, self)
        
        self.history.pop()  # 移除当前状态
        prev_record = self.history[-1][1]
        return self.cls.quick_load(prev_record, self)
    
    def get_last_action(self):
        return self.history[-1][0] if self.history else None
    
    def __repr__(self):
        return self.history.__repr__()
            

class GameEngine(Collector):
    """游戏引擎类 - 负责处理游戏的运行逻辑，包括动作处理"""
    def __init__(self, width=8, height=6):
        super().__init__(width, height)
        self.state = GameOutcome.Continue
        self.game_history = GameHistory(self)

    def deep_copy(self):
        return self.__class__.quick_load(self.quick_save())
    
    @classmethod
    def quick_load_helper(cls, raw_data):
        return super().quick_load(raw_data)
    
    @classmethod
    def quick_load(cls, raw_data, game_history=None):
        grid = cls.quick_load_helper(raw_data)
        if game_history is not None:
            grid.game_history = game_history
        else:
            grid.game_history = GameHistory(grid)
            # grid.game_history.add_init()
        return grid

    @classmethod
    def from_text(cls, text):
        grid = super().from_text(text)
        grid.state = GameOutcome.Continue
        grid.game_history = GameHistory(grid)
        grid.game_history.add_init()

        return grid
    
    # ====== 运行逻辑 ======
    def step(self, action):
        # return (Gridmap, GameOutcome, ChainInfo)
        if action.is_special():
            return getattr(self, '_handle_' + action.name)()
        return self._handle_movement(action)


    def _handle_movement(self, action):

        push_chain = {}

        if self.state != GameOutcome.Continue:
            return self, self.state, push_chain
        
        # 处理移动
        agents = action.sort_entities(self.get_agent())
        for you in agents:
            chain_info, you_coord = [], you.coord.to_pair()
            self._push_chain([you], action, chain_info)
            title = tuple(list(you_coord) + [action.value])
            push_chain[title] = chain_info
        # 处理规则
        self.rule_manager.update_all_rules()

        # 处理碰撞
        for _, tile in self.iter_tiles():
            if tile.check_collisions() == GameOutcome.Win:
                self.state = GameOutcome.Win
        if self.count_agent() == 0:
            self.state = GameOutcome.Defeat

        self.game_history.add_record(action, self)

        return self, self.state, push_chain

    def _push_chain(self, pusher, action, chain_info):
        
        next_tile = action.get_neighbor_tile(pusher[0], self)
        if not next_tile.is_empty():
            chain_info += next_tile.quick_save()

        prop = next_tile.get_prop()
        # 1：STOP交互（新增了边界）
        if 'STOP' in prop:
            return False
        # 2：PUSH交互
        if 'PUSH' in prop or 'TEXT' in prop:
            to_push = [e for e in next_tile.get_all_entities() 
                       if e.has_prop('PUSH') or e.has_prop('TEXT')]
            if not self._push_chain(to_push, action, chain_info):
                return False
        # 3: OTHER交互
        for y in pusher:
            self.move_entity(y, next_tile.coord)
        return True
    
    def _special_push_chain(self, action_value):
        return {(-4, -4, action_value): []}  # 固定一个特殊坐标表示非移动操作
        # return {(e.get_x(), e.get_y(), action_value): [] for e in self.get_agent()}

    def _handle_quit(self):
        self.state = GameOutcome.Quit
        self.game_history.add_record(Action.logout, self)
        return self, self.state, self._special_push_chain('q')

    def _handle_restart(self):
        init_grid = self.game_history.restart_record()
        return init_grid, init_grid.state, self._special_push_chain('r')
    
    def _handle_wait(self):
        self.game_history.add_record(Action.wait, self)
        return self, self.state, self._special_push_chain(' ')
    
    def _handle_undo(self):
        last_grid = self.game_history.undo_record()
        return last_grid, last_grid.state, self._special_push_chain('z')

    def get_possible_actions(self):
        if self.state == GameOutcome.Continue:
            return {'w': 'up', 'a': 'left', 's': 'down', 'd': 'right', 'q': 'quit', 'r': 'restart', 'z': 'undo'}
        return {'q': 'quit', 'r': 'restart', 'z': 'undo'}