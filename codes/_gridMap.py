from codes.base_entity import Entity, EntityType, Coord, Property
from enum import Enum
from codes.base_rule import RuleManager, Rule, NounIsNoun, NounIsProperty
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
        if self.is_special():
            return coord
        return getattr(coord, self.name)
    
    def get_neighbor_tile(self, item, gridmap):
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
    
    def __repr__(self):
        return self.name[0]

class Tile:
    def __init__(self, coord, gridmap,  entities=None):

        self.gridmap = gridmap
        self.size = (gridmap.width, gridmap.height)
        self.coord = Coord.from_tuple(coord, self.size)
        self.entities = entities or []
    
    def get_coord(self):
        return self.coord

    @property
    def prop(self):
        return Property.union([entity.get_prop() for entity in self.entities])

    def get_prop(self):
        return self.prop
    
    def get_prop_set(self):
        return self.prop._props
    
    def get_prop_one_hot(self):
        if self.is_empty():
            entity = Entity('.', self.get_coord(), ['Empty'])
            return [entity.get_prop_one_hot()]
        return [entity.get_prop_one_hot() for entity in self.get_all_entities()]

    def get_sim(self, tile, method='pair', id_weight=0.4):
        a = self.get_all_entities() if not self.is_empty() else [Entity('.', self.get_coord(), ['Empty'])]
        b = tile.get_all_entities() if not tile.is_empty() else [Entity('.', tile.get_coord(), ['Empty'])]
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
        self.entities.append(entity)
        self.gridmap.entities.append(entity)
        entity.tile = self
    
    def remove_entity(self, entity):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be an Entity'
        self.entities.remove(entity)
        self.gridmap.entities.remove(entity)
        entity.tile = None
    
    def clear_entities(self):
        for entity in self.get_all_entities():
            self.remove_entity(entity)

    def __len__(self):
        return len(self.entities)
    
    def equal_by_prop(self, other):
        assert isinstance(other, Tile), 'other must be a Block'
        if self.is_empty() != other.is_empty():
            return False
        return self.prop.get() == other.prop.get()

    def __eq__(self, other):
        return self.equal_by_prop(other)
    
    def get_all_entities(self):
        return self.entities.copy()

    def get_first_entity(self):
        if len(self.entities) > 0:
            return self.entities[0]

    def get_example_entity_id(self):
        if len(self.entities) == 0:
            return 'o'
        if len(self.entities) >= 2:
            return '?'
        return self.get_first_entity().get_entity_id()
    
    def get_token(self):
        for entity in self.entities:
            if entity.is_text():
                return entity.get_entity_id()
        return ' '
    
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
        return len(self.entities) == 0
    
    def is_token(self):
        return any(entity.is_text() for entity in self.entities)
    
    def is_single(self):
        return len(self.entities) == 1
    
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
        self[coord] = block
        return block

class GameEngine:
    def __init__(self, width = 8, height = 6):
        self.size = (width, height)
        self.width, self.height = width, height

        self.entities = []
        self.tiles = TileDict(self)
        self.rule_manager = RuleManager(self)
        self.game_history = [(Action.restart, self.quick_save())]
    
    # ====== 存储读取 ======

    def update_rules(self):
        self.rule_manager.update_rules()

    def quick_save(self):
        record = []
        for entity in self.entities:
            record.append(entity.quick_save())
        return (self.size, record)

    @classmethod
    def quick_load(cls, data):
        size, record = data
        grid = cls(size[0], size[1])
        for entity_data in record:
            entity = Entity.quick_load(entity_data)
            grid.add_entity(entity)
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
    def add_entity(self, entity):
        assert isinstance(entity, Entity), 'entity must be an Entity'
        entity.gridmap_init(self)
        self.tiles[entity.get_coord()].add_entity(entity)
    
    def remove_entity(self, entity):
        assert isinstance(entity, Entity) and entity in self.entities, 'entity must be in the gridmap'
        self.tiles[entity.get_coord()].remove_entity(entity)
    
    def move_entity(self, entity, coord):
        self.remove_entity(entity)
        entity.set_coord(coord)
        self.add_entity(entity)

    # ====== 获取信息 ======
    def get_size(self):
        return self.size
    
    def get_all_entities(self):
        return self.entities.copy()
    
    def get_entities_by_id(self, target):
        target = target.get_entity_id() if isinstance(target, Entity) else target
        return list([entity for entity in self.entities if entity.get_entity_id() == target])
    
    def get_entities_by_prop(self, target):
        if isinstance(target, Entity):
            target = target.get_prop()
        return list([entity for entity in self.entities if entity.has_prop(target)])
    
    def get_tile(self, coord):
        if coord is None:
            return None
        return self.tiles[Coord.from_tuple(coord, self.size)]
    
    def get_empty_coords(self):
        return {coord for coord, tile in self.tiles.items() if tile.is_empty()}
    
    def iter_tiles(self):
        yield from self.tiles.items()
    
    # ====== 核心地图 ======
    def step(self, action):
        # return (Gridmap, GameOutcom, Dict)
        if action.is_special():
            return getattr(self, '_handle_' + action.name)()
        return self._handle_movement(action)

    def _handle_movement(self, action):
        info = {'event': 'movement', 'push_chain': []}
        outcome = GameOutcome.Continue
        you= self.get_entities_by_prop('YOU')

        sorted_you = action.sort_entities(you)
        for you in sorted_you:
            chain_info = {'chain_list': [], 'finished': False}
            chain_info['finished'] = self._push_chain(you, action, chain_info)
            info['push_chain'].append(chain_info)
        self.rule_manager.update_rules()
        for tile in self.tiles.values():
            if tile.check_collisions() == GameOutcome.Win:
                outcome = GameOutcome.Win

        self.game_history.append((action, self.quick_save()))
        you = self.get_entities_by_prop('YOU')
        if len(you) == 0:
            outcome = GameOutcome.Defeat
        return self, outcome, info

    def _push_chain(self, pusher, action, chain_info):
        
        pusher = [pusher] if isinstance(pusher, Entity) else pusher
        next_tile = action.get_neighbor_tile(pusher[0], self)

        # 1：None条件无交互
        if next_tile is None:
            node = {'pusher': pusher, 'pushed': [], 'blocked_by': 'Boundary'}
            chain_info['chain_list'].insert(0, node)
            return False

        prop = next_tile.get_prop()
        node = {'pusher': pusher, 'pushed': next_tile.get_all_entities(), 'blocked_by': None}

        # 2：STOP交互
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
    
class Gridmap(GameEngine):
    # class-level index mapping state_key -> summary (shared across subclasses)
    state_index = {}
    # lock to protect concurrent access to state_index
    _state_index_lock = threading.RLock()

    def _check_yous(self):
        all_you = self.get_entities_by_prop('YOU')
        if not all_you:
            return None
        return all_you[0].get_coord()
    
    def _get_basic_counts(self):
        PROP_KEYS = ['YOU', 'WIN', 'DEFEAT', 'PUSH', 'STOP', 'TEXT', 'REGULAR']
        counts = {prop: 0 for prop in PROP_KEYS}
        for prop in PROP_KEYS:
            counts[prop] = len(self.get_entities_by_prop(prop))
        return counts

    def _get_distances(self):
        """
        合并的距离计算方法
        一次性计算 man_distance 和 game_distance
        返回: (man_dist, man_reach, reachable_count, game_dist, game_reach)
        """
        # 获取 YOU 对象（只查询一次）
        all_you = self.get_entities_by_prop('YOU')
        num_objects = len(self.get_all_entities())
        # 初始化结果字典
        man_dist_dict = {prop: float('inf') for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']}
        game_dist_dict = {prop: float('inf') for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']}
        
        if not all_you:
            # 没有 YOU 对象时，返回默认值
            man_reach_dict = {prop: 0 for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']}
            game_reach_dict = {prop: 0 for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']}
            return (num_objects, man_dist_dict, man_reach_dict, 0, game_dist_dict, game_reach_dict)
        
        # 初始化起点
        you_coords = [you.get_coord() for you in all_you]
        
        # === BFS 1: Man Distance (所有邻居都传播) ===
        man_queue = Deque()
        man_visited = set()
        for coord in you_coords:
            man_queue.push((coord, 1))
            for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']:
                if self.get_tile(coord).has_prop(prop):
                    man_dist_dict[prop] = 0
        man_visited.update(you_coords)
        
        while not man_queue.isEmpty():
            coord, dist = man_queue.pop()
            for neighbor_coord in coord.neighbors:
                if neighbor_coord is None or neighbor_coord in man_visited:
                    continue
                man_visited.add(neighbor_coord)
                neighbor_tile = self.get_tile(neighbor_coord)
                man_queue.push((neighbor_coord, dist + 1))
                
                if neighbor_tile.is_empty():
                    continue
                
                # 更新距离
                for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']:
                    if neighbor_tile.has_prop(prop) and man_dist_dict[prop] > dist:
                        man_dist_dict[prop] = dist
        
        # === BFS 2: Game Distance (只有空格子传播) ===
        game_queue = Deque()
        game_visited = set()
        reachable = set()
        for coord in you_coords:
            game_queue.push((coord, 1))
            for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']:
                if self.get_tile(coord).has_prop(prop):
                    game_dist_dict[prop] = 0
        game_visited.update(you_coords)
        reachable.update(you_coords)
        
        while not game_queue.isEmpty():
            coord, dist = game_queue.pop()
            for neighbor_coord in coord.neighbors:
                if neighbor_coord is None or neighbor_coord in game_visited:
                    continue
                game_visited.add(neighbor_coord)
                neighbor_tile = self.get_tile(neighbor_coord)
                
                if neighbor_tile.is_empty():
                    # 空格子继续传播
                    game_queue.push((neighbor_coord, dist + 1))
                    continue
                
                # 非空格子加入可达集合
                reachable.add(neighbor_coord)
                for prop in ['DEFEAT', 'WIN', 'PUSH', 'STOP', 'TEXT', 'REGULAR']:
                    if neighbor_tile.has_prop(prop) and game_dist_dict[prop] > dist:
                        game_dist_dict[prop] = dist
        
        # 计算 reach 值
        man_reach_dict = {prop: 1/dist if dist > 0 else float('inf') for prop, dist in man_dist_dict.items()}
        game_reach_dict = {prop: 1/dist if dist > 0 else float('inf') for prop, dist in game_dist_dict.items()}
        
        # 组装结果
        return (num_objects,man_dist_dict, man_reach_dict, len(reachable), game_dist_dict, game_reach_dict)
    
    def _get_man_distance(self):
        """获取曼哈顿距离（调用合并方法）"""
        num_objects, man_dist, man_reach, _, _, _ = self._get_distances()
        return num_objects, man_dist, man_reach

    def _get_game_distance(self):
        """获取游戏距离（调用合并方法）"""
        _, _, _, reachable_count, game_dist, game_reach = self._get_distances()
        return reachable_count, game_dist, game_reach

    def _get_interaction(self):
        """
        从所有 YOU 的位置出发，沿空格传播（与 game distance 相同的传播规则），
        在遇到第一个非空格子时，记录为一个 Interaction 目标。

        返回:
            List[Interaction]: 在可达空格传播边界上发现的 Interaction 对象列表。
        """
        all_you = self.get_entities_by_prop('YOU')
        if not all_you:
            return []

        you_coords = [you.get_coord() for you in all_you]

        queue = Deque()
        visited = set()
        interactions = []

        for coord in you_coords:
            queue.push((coord, 1))
            visited.add(coord)
        # visited only tracks empty tiles (per new logic)

        while not queue.isEmpty():
            coord, dist = queue.pop()
            # 显式按四个方向扫描邻居
            for action in (Action.up, Action.down, Action.left, Action.right):
                neighbor_coord = action.get_neighbor_coord(coord)
                if neighbor_coord is None:
                    continue

                if neighbor_coord not in visited:  
                    neighbor_tile = self.get_tile(neighbor_coord)
                    if neighbor_tile.is_empty():
                        visited.add(neighbor_coord)
                        queue.push((neighbor_coord, dist + 1))
                        continue
                    
                    # 遇到非空格子，创建 Interaction 目标（以当前 coord 和 action 为起点/方向）
                    interactions.append(Interaction(coord, action, dist, self))

        return len(interactions), interactions

    def _get_state_hash(self, updating = True):
        """
        获取游戏状态的哈希键
        基于 quick_save() 的结果，转换为可哈希的格式
        """
        # Use deterministic JSON serialization of the quick_save() output
        # and return the SHA-256 hex string so the key is stable across
        # processes and persistent storage.
        size, record = self.quick_save()
        data = {'size': [int(size[0]), int(size[1])],
            'record': [(ent_id, [int(coord[0]), int(coord[1])]) for ent_id, coord in record]}
        b = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        full_digest = hashlib.sha256(b).hexdigest()
        # Truncate to configured hex length to produce shorter keys (may increase collision risk)
        state_key = full_digest[:STATE_HASH_HEX_LENGTH]

        # If we haven't yet stored a summary for this state, compute and cache it.
        # We avoid recursion by passing the precomputed key into summary().
        if state_key not in Gridmap.state_index and updating:
            s = self.summary(precomputed_state_key=state_key)
            Gridmap.state_index[state_key] = s
        return state_key
    
    def _get_rules(self):
        rules = self.rule_manager.get_all_rules(rule_type = 'noun_is_property')
        props = [rule.get_property().upper() for rule in rules]
        return len(rules), props
    
    def summary(self, precomputed_state_key=None):
        """Return a serializable summary of current state.

        The summary includes:
        - state_key: repr(self.get_state_hash())
        - raw: quick_save() result (if available)
        - distances: result of _get_distances()
        - interactions: list of simplified interactions
        - num_entities: number of entities in grid
        """
        # state key (string) -- use provided precomputed key if available to avoid
        # calling _get_state_hash() (which may call summary when caching).

        if precomputed_state_key is None:
            state_key = self._get_state_hash(updating=False)
        else:
            state_key = precomputed_state_key
        cached = Gridmap.state_index.get(state_key)
        if cached is not None:
            return cached
        
        PROP_KEYS = ['WIN', 'DEFEAT', 'PUSH', 'STOP', 'TEXT', 'REGULAR']

        # info
        num_rules, rules = self._get_rules()
        num_objects, man_dist, _, num_reachable, game_dist, _ = self._get_distances()
        man_dist_list = [man_dist[k] for k in PROP_KEYS]
        game_dist_list = [game_dist[k] for k in PROP_KEYS]
        you = self._check_yous()
        you_coord = (int(you.x), int(you.y)) if you else None
        info = {'num_rule': num_rules, 'rules': rules, 'you': you_coord,
                'num_object': num_objects, 'man_dist': man_dist_list,
                'num_reachable': num_reachable, 'game_dist': game_dist_list}
        
        # interactions
        num_inter, inters = self._get_interaction()
        inter_list = [inter._get_chain_index() for inter in inters]
        inter = {'num_inter': num_inter, 'inters': inter_list}
        summary_dict = {'state_key': state_key, 'info': info, 'inter': inter}
        Gridmap.state_index[state_key] = summary_dict
        return summary_dict

    @classmethod
    def clear_state_index(cls):
        cls.state_index = {}


    @classmethod
    def state_state_index(cls, mapping, replace=False):
        """Bulk-set the class-level state_index.

        Args:
            mapping (dict): mapping from state_key -> summary (or serializable value)
            replace (bool): if True, replace the existing index entirely; if False, merge/update.

        Returns:
            int: number of entries in the resulting state_index

        This method is thread-safe (uses an RLock) and is intended for fast bulk
        loading of precomputed summaries (for example when loading from disk).
        """
        if mapping is None:
            return len(cls.state_index)
        if not isinstance(mapping, dict):
            raise TypeError('mapping must be a dict')

        with cls._state_index_lock:
            if replace:
                cls.state_index = dict(mapping)
            else:
                # Merge: mapping keys overwrite existing keys
                cls.state_index.update(mapping)
            return len(cls.state_index)

    @classmethod
    def get_state_summary(cls, state_key, default=None):
        """Thread-safe lookup of a summary by state_key."""
        with cls._state_index_lock:
            return cls.state_index.get(state_key, default)

    @classmethod
    def save_state_index_json(cls, path, indent=2):
        """Save the entire state_index to a JSON file.

        Each entry is written as state_key -> summary (nested JSON). This is thread-safe.
        Returns the number of entries written.
        """
        with cls._state_index_lock:
            data = dict(cls.state_index)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return len(data)

    @classmethod
    def load_state_index_json(cls, path, merge=True):
        """Load state_index entries from a JSON file.

        If merge is True, entries are merged into existing index (incoming keys overwrite).
        If merge is False, replace the entire index.
        Returns the number of entries after load.
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('JSON state index must be an object mapping keys -> summaries')
        with cls._state_index_lock:
            if merge:
                cls.state_index.update(data)
            else:
                cls.state_index = dict(data)
            return len(cls.state_index)

    @classmethod
    def save_state_index_parquet(cls, path):
        """Save state_index to a Parquet file (columns: state_key, summary_json).

        Requires pandas and a parquet engine (pyarrow or fastparquet). Summary is stored as JSON string.
        Returns number of rows written.
        """
        try:
            import pandas as pd
        except Exception as e:
            raise ImportError('pandas is required to write parquet; please install pandas and pyarrow') from e

        with cls._state_index_lock:
            items = [(k, json.dumps(v, ensure_ascii=False)) for k, v in cls.state_index.items()]
        df = pd.DataFrame(items, columns=['state_key', 'summary_json'])
        df.to_parquet(path, index=False)
        return len(df)

    @classmethod
    def load_state_index_parquet(cls, path, merge=True):
        """Load state_index from a Parquet file written by save_state_index_parquet.

        If merge is True, incoming rows overwrite existing keys. Returns number of entries after load.
        """
        try:
            import pandas as pd
        except Exception as e:
            raise ImportError('pandas is required to read parquet; please install pandas and pyarrow') from e

        df = pd.read_parquet(path)
        if 'state_key' not in df.columns or 'summary_json' not in df.columns:
            raise ValueError('Parquet file must contain columns: state_key, summary_json')
        data = {row['state_key']: json.loads(row['summary_json']) for _, row in df.iterrows()}
        with cls._state_index_lock:
            if merge:
                cls.state_index.update(data)
            else:
                cls.state_index = dict(data)
            return len(cls.state_index)

    @classmethod
    def save_state_index_sqlite(cls, path, table='state_index'):
        """Save state_index into a SQLite database table with columns (state_key TEXT PRIMARY KEY, summary_json TEXT).

        Existing table will be created if missing. This method writes entries in a transaction.
        Returns number of rows written.
        """
        import sqlite3
        with cls._state_index_lock:
            items = [(k, json.dumps(v, ensure_ascii=False)) for k, v in cls.state_index.items()]
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            cur.execute(f"CREATE TABLE IF NOT EXISTS {table} (state_key TEXT PRIMARY KEY, summary_json TEXT)")
            cur.executemany(f"REPLACE INTO {table} (state_key, summary_json) VALUES (?, ?)", items)
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    @classmethod
    def load_state_index_sqlite(cls, path, table='state_index', merge=True):
        """Load state_index entries from a SQLite DB file. If merge is False, replace existing index.

        Returns number of entries after load.
        """
        import sqlite3
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if cur.fetchone() is None:
                return len(cls.state_index)
            cur.execute(f"SELECT state_key, summary_json FROM {table}")
            rows = cur.fetchall()
            data = {k: json.loads(v) for k, v in rows}
            with cls._state_index_lock:
                if merge:
                    cls.state_index.update(data)
                else:
                    cls.state_index = dict(data)
                return len(cls.state_index)
        finally:
            conn.close()

class Interaction:
    def __init__(self, start, action, dist, gridmap):
        self.start = start
        self.action = action
        self.dist = dist
        self.gridmap = gridmap
        self.chain, current= [], action.get_neighbor_coord(start)
        self.collision = action.get_neighbor_coord(start)
        while current is not None:
            tile = gridmap.get_tile(current)
            if not tile.is_empty():
                self.chain.append(tile)
            if not(tile.has_prop('PUSH') or tile.has_prop('TEXT')):
                break
            current = action.get_neighbor_coord(current)

        self.direct = self.chain[0] if self.chain else []
        self.indirect = self.chain[1:] if self.direct else []

    def _get_chain_index(self):
        """Return readable composite index: statehash_actionname_collisioncoord"""
        pre_state = self.gridmap._get_state_hash(updating=False)
        action_name = self.action.name
        coord = f"{int(self.collision.x)}_{int(self.collision.y)}" if self.collision else "None"
        return f"{pre_state}_{action_name}_{coord}"

    def _get_content(self):

        direct_ent = self.direct.get_all_entities() if self.direct else []
        indirect_ent = [tile.get_all_entities() for tile in self.indirect]
        total_ent = direct_ent + indirect_ent

        direct_prop = self.direct.get_prop().get() if self.direct else []
        indirect_set = set()
        for tile in self.indirect:
            indirect_set.update(tile.get_prop_set())
        indirect_prop = sorted(indirect_set)
        total_prop = sorted(set(direct_prop + indirect_prop))

        return {'len_chain': len(self.chain), 'full_ent': len(total_ent), 'full_prop': total_prop,
                'direct_ent': len(direct_ent), 'indirect_ent': len(indirect_ent),
                'direct_prop': direct_prop, 'indirect_prop': indirect_prop}
    
    def simulation(self, limit = 1):
        sim_grid = Gridmap.quick_load(self.gridmap.quick_save())
        num_of_try, state_record = 0, [None] * limit
        you_entities = sim_grid.get_entities_by_prop('YOU')
        you_entity = you_entities[0] if you_entities else None
        sim_grid.move_entity(you_entity, self.start)
        while num_of_try < limit:
            sim_grid, outcome, _ = sim_grid.step(self.action)
            state_record[num_of_try] = sim_grid._get_state_hash(updating=False)
            num_of_try += 1
            if outcome != GameOutcome.Continue:
                break
        return state_record
    
    def _get_transition(self):
        pre_state = self.gridmap._get_state_hash()
        post_state = self.simulation(limit = 1)[0]
        return {'pre_state': pre_state, 'post_state': post_state,
                'dist': self.dist, 'action': self.action.name, 'collision': self.collision}

    
    def get_description(self):
        text = f'Dist={self.dist}->{str(self.start)}->' if self.direct else 'Move'
        
        if self.direct:
            for entity in self.direct.get_all_entities():
                text += entity.get_description()
        if self.indirect:
            text += '->'
            for tile in self.indirect:
                for entity in tile.get_all_entities():
                    text += entity.get_description()
        return text
    
    def __repr__(self):
        return self.get_description()

        
