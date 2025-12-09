
class Property:
    FULLDICT =  {
        -1: 'EMPTY',
        30000: 'REGULAR', 
        30001: 'PUSH',
        30002: 'YOU', 
        30004: 'STOP',
        30003: 'WIN',
        30005: 'DEFEAT',
        30006: 'SINK',
        30007: 'HOT',
        30008: 'MELT',
        60000: 'REGULAR',
        60001: 'TEXT'
    }
    FULLSET = set(FULLDICT.values())
    EXISTDICT = set()

    ONEHOTDICT = {'YOU': 0, 'WIN': 1, 'PUSH': 2, 'DEFEAT': 3, 'STOP': 4, 'TEXT': 5, 'REGULAR': 6, 'EMPTY': 7}
    
    def __init__(self, items=None):
        items = items or ['REGULAR']
        self._props = {self.get_name(item) for item in items}
        self._regular_check()
        Property.EXISTDICT.update(self._props)
    
    # ====== 获得特定属性 ======
    def id_to_name(self, id):
        return self.FULLDICT.get(id, None)

    def get_name(self, item):
        if isinstance(item, int):
            item = self.id_to_name(item)
        item = item.upper()
        assert item in self.FULLSET, 'irregular property'
        return item
    
    # ====== 增减属性 ======
    def add(self, item):
        item = self.get_name(item)
        self._props.add(item)
        self._regular_check()
        Property.EXISTDICT.add(item)
    
    def remove(self, item):
        item = self.get_name(item)
        self._props.remove(item)
        self._regular_check()
    
    def clear(self):
        self._props.clear()
        self._regular_check()
    
    def _regular_check(self):
        if len(self) == 0:
            self._props.add('REGULAR')
        if 'REGULAR' in self._props and len(self) > 1:
            self._props.remove('REGULAR')

    # ====== 属性判断 ======
    def has(self, item):
        if isinstance(item, Property):
            item = item.get()
        if isinstance(item, list):
            return all(self.has(i) for i in item)
        item = self.get_name(item)
        return item in self._props
    
    def get(self):
        return sorted(self._props)
    
    def get_one_hot(self):
        one_hot = [0] * (len(self.ONEHOTDICT))
        for prop in self._props:
            if prop in self.ONEHOTDICT:
                one_hot[self.ONEHOTDICT[prop]] += 1
                if prop == 'TEXT':
                    one_hot[self.ONEHOTDICT['PUSH']] += 1
                if prop == 'EMPTY':
                    one_hot[self.ONEHOTDICT['REGULAR']] += 1
        return ''.join(map(str, one_hot))
    
    def cal_sim(self, prop):
        a = self.get_one_hot().split(' ')
        b = prop.get_one_hot().split(' ')
        inter = sum(x and y for x, y in zip(a, b))
        union = sum(x or y for x, y in zip(a, b))
        return 1.0 if union == 0 else inter / union
    
    def get_description(self):
        return ','.join(self.get())
    
    def __repr__(self):
        return self.get_description()
    
    def __len__(self):
        return len(self._props)
    
    def __contains__(self, item):
        return self.has(item)
    
    # ====== 属性标志 ======
    @property
    def flag(self):
        flag, base = 0, 1
        for property in Property.FULLSET:
            if property in self._props:
                flag += base
            base *= 2
        return flag
    
    def __eq__(self, other):
        assert isinstance(other, Property), 'other must be a Property'
        return self.get() == other.get()
    
    # ====== 属性合并 ======
    def __add__(self, other):
        assert isinstance(other, Property), 'other must be a Property'
        return Property(self._props | other._props)
    
    @classmethod
    def union(cls, instances):
        props = set()
        for p in instances:
            if isinstance(p, str):
                p = [p]
            if isinstance(p, list):
                p = cls(p)
            assert isinstance(p, cls), 'all instances must be Property'
            props.update(p._props)
        return cls(props)
    
class Coord(tuple):
    """坐标类, 继承自tuple, 提供便捷的坐标操作方法"""
    bound = False
    def __new__(cls, x, y, size=None):
        """创建新的坐标实例"""
        if size is not None:
            width, height = size
            if not (0 <= x < width and 0 <= y < height):
                return Boundary()

        return super().__new__(cls, (x, y))
    
    def __init__(self, x, y, size=None):
        """初始化坐标"""
        self.x, self.y = int(x), int(y)
        self.size = size
    
    def get_x(self):
        return self.x
    
    def get_y(self):
        return self.y

    def to_pair(self):
        """Return this Coord as an (int(x), int(y)) tuple."""
        return (self.x, self.y)

    @classmethod
    def from_tuple(cls, coord, size=None):
        """从元组创建坐标"""
        if isinstance(coord, cls) or isinstance(coord, Boundary):
            return coord
        return cls(*coord, size)

    @classmethod
    def to_pair(cls, coord):
        """Utility: convert a Coord (or None) to an (x,y) tuple or None.

        Usage: pair = Coord.pair_or_none(c)
        This replaces common patterns like: (int(c.x), int(c.y)) if c is not None else None
        """
        return (int(coord.x), int(coord.y))

    @property
    def left(self):
        """返回左边的坐标 (x - 1, y)"""
        return Coord(self.x - 1, self.y, self.size)
    @property
    def right(self):
        """返回右边的坐标 (x + 1, y)"""
        return Coord(self.x + 1, self.y, self.size)
    
    @property
    def up(self):
        """返回上边的坐标 (x, y - 1)"""
        return Coord(self.x, self.y + 1, self.size)
    
    @property
    def down(self):
        """返回下边的坐标 (x, y + 1)"""
        return Coord(self.x, self.y - 1, self.size)
    
    @property
    def neighbors(self):
        """返回所有相邻的坐标"""
        neighbor = [self.left, self.right, self.up, self.down]
        return [coord for coord in neighbor if coord]

    def set_size(self, size):
        assert self.boundary_check(size), 'size is not valid'
        self.size = size

    def boundary_check(self, size=None):
        width, height = size or self.size
        if not (0 <= self.x < width and 0 <= self.y < height):
            return False
        return True
    
    def manhattan(self, other):
        return abs(self.x - other.x) + abs(self.y - other.y)
    
    def __str__(self):
        """字符串表示"""
        return f"({self.x},{self.y})"
    
    def __repr__(self):
        """字符串表示"""
        return f"({self.x},{self.y})"

class Boundary:
    bound = True
    x, y = -1, -1
    def __repr__(self):
        return 'Boundary'
    def __bool__(self):
        return False
    def __eq__(self, other):
        return isinstance(other, Boundary)
    def __hash__(self):
        return hash('Boundary')
    


# class EntityID:
#     entitydict = None

#     def __call__(self, id):
#         if self.entitydict is None:
#             self.load_data()
#         return self.entitydict.loc[id, ['Type', 'Symbol', 'Texture', 'Sprite']]
    
#     def load_data(self):
#         ROOT = 'E:/PYTHON项目/BABAISYOU/baba-main-datasample-uniqueid-hz'
#         sys.path.append(ROOT)
#         PATH = '../pybaba/entitydict.csv'
#         EntityID.entitydict = pd.read_csv(PATH, index_col=1)

class EntityType:
    OBJECT = 0
    NOUN = 1
    OPERATOR = 2
    PROPERTY = 3

    NOUNDICT = {
        'A': 'Glass',
        'B': 'Bone',
        'C': 'Cloud',
        'D': 'Dice',
        'F': 'Football',
        'G': 'Glove',
        'H': 'Heart',
        'K': 'Book',
        'L': 'Lemon',
        'M': 'Mirror',
        'N': 'Fan',
        'P': 'Pumpkin',
        'S': 'Sun',
        'W': 'Kiwi',
        'X': 'Box',

    }
    OBJECTDICT = {k.lower(): v.lower() for k, v in NOUNDICT.items()}
    PROPERTYDICT = {
        '`': 'Regular',
        '!': 'Text',
        '#': 'Boundary',
        '1': 'Push',
        '2': 'You',
        '4': 'Stop',
        '3': 'Win',
        '5': 'Defeat'
    }
    OPERATORDICT = {
        '0': 'IS'
    }
    ATTRIBUTEDICT = {**PROPERTYDICT, **NOUNDICT}
    TEXTDICT = {**NOUNDICT, **PROPERTYDICT, **OPERATORDICT}


    @classmethod
    def from_char(cls, char):
        char = char.strip()
        if char.islower():
            return cls.OBJECT, cls.OBJECTDICT[char]
        if char.isupper():
            return cls.NOUN, cls.NOUNDICT[char]
        if char in ['0']:
            return cls.OPERATOR, cls.OPERATORDICT[char]
        if char in '123456789':
            return cls.PROPERTY, cls.PROPERTYDICT[char]
        if char in ['.']:
            return -1, 'Empty'
        if char in ['#']:
            return -1, 'Bound'
        else:
            return None
    @staticmethod
    def noun2object(noun):
        return noun.lower()
    
    def object2noun(object):
        return object.upper()


class Entity:

    def __init__(self, id='.', coord=(0, 0), global_id=None, prop=None):

        self.type, self.full_name = EntityType.from_char(id)
        self.entity_id = id
        self.coord = Coord.from_tuple(coord)
        self.prop = Property(prop)

        self.gridmap, self.tile = None, None
        self.global_id = global_id

    # ====== 上级操作 ======
    def gridmap_init(self, gridmap):
        self.gridmap = gridmap
        self.coord.set_size((gridmap.width, gridmap.height))
        self.tile = gridmap.get_tile(self.coord)

        if self.is_text():
            self.add_prop('TEXT')

    def get_tile(self):
        return self.tile
    
    def get_gridmap(self):
        return self.gridmap
    
    def get_entity_id(self):
        return self.entity_id
    
    def get_full_name(self):
        return self.full_name
    
    # ====== 类型判断 ======
    def is_text(self):
        return self.type in [EntityType.NOUN, EntityType.PROPERTY, EntityType.OPERATOR]
    def is_object(self):
        return self.type == EntityType.OBJECT
    def is_operator(self):
        return self.type == EntityType.OPERATOR
    def is_property(self):
        return self.type == EntityType.PROPERTY
    
    def get_object_id(self):
        assert self.is_noun(), 'entity is not a noun'
        return self.entity_id.lower()
    
    def get_noun_id(self):
        assert self.is_object(), 'entity is not a object'
        return self.entity_id.upper()
    
    # ====== 坐标操作 ======
    def get_coord(self):
        return self.coord
    
    def get_x(self):
        return self.coord.get_x()
    
    def get_y(self):
        return self.coord.get_y()
    
    def set_coord(self, coord):
        self.coord = Coord.from_tuple(coord)

    # ====== 属性操作 ======
    def get_identity(self):
        if self.is_text():
            return 'Text'
        return self.full_name

    def get_prop(self):
        return self.prop.get()
    
    def get_prop_set(self):
        return self.prop._props
    
    def get_prop_one_hot(self):
        return self.prop.get_one_hot()
    
    def add_prop(self, prop):
        self.prop.add(prop)
    
    def remove_prop(self, prop):
        self.prop.remove(prop)
    
    def has_prop(self, prop):
        return self.prop.has(prop)

    def clear_prop(self):
        self.prop.clear()
        if self.is_text():
            self.add_prop('TEXT')

    # ====== 存储读取 ======
    def quick_save(self):
        return f"{self.global_id}:{self.entity_id},{self.get_x()},{self.get_y()}"

    @classmethod
    def quick_load(cls, data):
        global_id, data = data.split(':')
        entity_id, x, y = data.split(',')
        return cls(entity_id, Coord(int(x), int(y)), int(global_id))
    
    def get_description(self, exact = True):
        if not exact and self.is_text():
            return f'@{self.get_coord()}: TEXT [{self.prop.get_description()}]'
        return f'@{self.get_coord()}: {self.get_full_name()} [{self.prop.get_description()}]'
    
    def __str__(self):
        return self.get_description()
    
    def __repr__(self):
        return self.get_description()
    
    # ===== 相似度计算 ======
    def cal_sim(self, entity, id_weight = 0.4):
        prop_sim = self.prop.cal_sim(entity.prop)
        id_sim = 1.0 if self.entity_id == entity.entity_id else 0.0
        return id_weight * id_sim + (1 - id_weight) * prop_sim
    
    def equal_prop(self, entity):
        return self.prop == entity.prop
    
    def equal_id(self, entity):
        return self.entity_id == entity.entity_id
    
    def equal_global(self, entity):
        return self.global_id == entity.global_id
    
    def equal(self, entity):
        return self.equal_prop(entity) and self.equal_id(entity) and self.equal_global(entity)

    def __eq__(self, other):
        return self.equal(other)