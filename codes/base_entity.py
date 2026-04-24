import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Tuple, Union
from util import encoding, decoding

class Property:

    VALIDDICT = {'YOU': 0, 'WIN': 1, 'PUSH': 2, 'DEFEAT': 3, 'STOP': 4, 'TEXT': 5, 'REGULAR': 6, 'EMPTY': 7}
    VALIDLIST = list(VALIDDICT.keys())
    REGULAR = 1<<VALIDDICT['REGULAR']
    EMPTY = 1<<VALIDDICT['EMPTY']
    TEXT = 1<<VALIDDICT['TEXT']
    STOP = 1<<VALIDDICT['STOP']

    # ====== 和字符串列表相互转化 ======

    @classmethod 
    def from_list(cls, prop_list: list) -> 'Property':
        return cls(sum(cls.prop2flag(prop) for prop in prop_list))
    
    @property
    def prop_lst(self):
        return [prop for prop, i in Property.VALIDDICT.items() if self._flag & (1 << i)]


    # ====== 修改属性 ======
    def clear(self):
        self._flag = self.default
        self._regular_check()
    
    def add(self, item: Union[str, list]):
        if isinstance(item, list):
            for i in item:
                self._flag |= self.prop2flag(i)
        else:
            self._flag |= self.prop2flag(item)
        self._regular_check()
    
    def remove(self, item: Union[str, list]):
        if isinstance(item, list):
            for i in item:
                self._flag &= ~self.prop2flag(i)
        else:
            self._flag &= ~self.prop2flag(item)
        self._regular_check()
    
    def update(self, item: 'Property'):
        self._flag = self.default | item._flag
        self._regular_check()

    def union(self, item: int):
        self._flag |= item
        self._regular_check()
        return self
    
    @classmethod
    def union_props(cls, props: list) -> 'Property':
        result_flag = 0
        for prop in props:
            flag = prop._flag if isinstance(prop, Property) else prop
            result_flag |= flag
        return cls(result_flag)
    
    # ====== 获取属性 ======

    def get_description(self):
        return '+'.join(map(str.lower, self.prop_lst))
    
    def __len__(self):
        return len(self.prop_lst)
    
    def __contains__(self, item):
        return bool(self._flag & self.prop2flag(item))
    
    def __eq__(self, other):
        assert isinstance(other, Property), 'other must be a Property'
        return self._flag == other._flag
    
    def __str__(self):
        return str(self._flag)
    
    def __repr__(self):
        return self.get_description()
    
    @classmethod
    def prop2flag(cls, prop: str) -> int:
        return 1 << cls.VALIDDICT[prop]

    # ====== 内部方法 ======
    def __init__(self, value: int = 0):
        self.default = int(value or 0)
        self.clear()

    def _regular_check(self):
        if self._flag == 0:
            self._flag |= self.REGULAR
        if self._flag != self.REGULAR:
            self._flag &= ~self.REGULAR

    
class Coord(tuple):
    """坐标类, 继承自tuple, 提供便捷的坐标操作方法"""
    bound = False
    def __new__(cls, coord, size=None):

        width, height = size if size else (float('inf'), float('inf'))
        if not (0 <= coord[0] < width and 0 <= coord[1] < height):
            ins = Boundary.__new__(Boundary)
            ins.__init__()
            return ins
        return super().__new__(cls, coord)
    
    def __init__(self, coord, size=None):
        """初始化坐标"""
        self.x, self.y = int(coord[0]), int(coord[1])
        self.size = size

    def set_size(self, size):
        assert (0 <= self.x < size[0] and 0 <= self.y < size[1]), 'invalid size'
        self.size = size

    @property
    def neighbors(self):
        """返回所有相邻的坐标"""
        neighbor = [self.left, self.right, self.up, self.down]
        return [coord for coord in neighbor if coord]

    
    def get_x(self):
        return self.x
    
    def get_y(self):
        return self.y

    def to_pair(self):
        return (self.x, self.y)

    @property
    def left(self):
        """返回左边的坐标 (x - 1, y)"""
        return Coord((self.x - 1, self.y), self.size)
    @property
    def right(self):
        """返回右边的坐标 (x + 1, y)"""
        return Coord((self.x + 1, self.y), self.size)
    
    @property
    def up(self):
        """返回上边的坐标 (x, y - 1)"""
        return Coord((self.x, self.y + 1), self.size)
    
    @property
    def down(self):
        """返回下边的坐标 (x, y + 1)"""
        return Coord((self.x, self.y - 1), self.size)

    def manhattan(self, other):
        return abs(self.x - other.x) + abs(self.y - other.y)


class Boundary(Coord):
    bound = True
    def __new__(cls, coord=None, size=None):
        return tuple.__new__(cls, (-1, -1))
    
    def __init__(self, coord=None, size=None):
        self.x, self.y, self.size = -1, -1, size

    def __repr__(self): return 'Boundary'
    def __bool__(self): return False
    @property
    def neighbors(self): return None
    
    
class Material:

    OBJECT = 'object'
    NOUN = 'noun'
    OPERATOR = 'operator'
    PROPERTY = 'property'
    SPECIAL = 'special' # 不需要定义 texture 的entity

    def __init__(self, name):
        assert name in self.TYPEDICT, f'Irregular material name: {name}'
        self.type = self.TYPEDICT[name]
        self.short_name = name
        self.full_name = self.FULLDICT[self.type][name]
        self.texture = f"en_{self.type}_{self.full_name}.png"

    def get_description(self):
        return self.full_name

    def __repr__(self):
        return self.get_description()
    def __str__(self):
        return self.short_name

    # ====== 类型判断与转化 ======
    def is_text(self):
        return self.type in [self.NOUN, self.PROPERTY, self.OPERATOR]
    def is_attribute(self):
        return self.type in [self.PROPERTY, self.NOUN]
    
    def is_noun(self):
        return self.type is self.NOUN
    def is_object(self):
        return self.type is self.OBJECT
    
    def is_operator(self):
        return self.type is self.OPERATOR
    def is_property(self):
        return self.type is self.PROPERTY
    def is_special(self):
        return self.type is self.SPECIAL

    def to_noun(self):
        return self.short_name.upper() if self.is_object() else self.short_name
    def to_object(self):
        return self.short_name.lower() if self.is_noun() else self.short_name

    # ====== 基本属性 ======

    FULLDICT = {
        
        OBJECT: {
            'a': 'glass',
            'b': 'bone',
            'c': 'cloud',
            'd': 'dice',
            'f': 'football',
            'g': 'glove',
            'h': 'heart',
            'k': 'book',
            'l': 'lemon',
            'm': 'mirror',
            'n': 'fan',
            'p': 'pumpkin',
            's': 'sun',
            'w': 'kiwi',
            'x': 'box',
        }, 

        PROPERTY: {
            '1': 'PUSH',
            '2': 'YOU',
            '4': 'STOP',
            '3': 'WIN',
            '5': 'DEFEAT'
        }, 

        OPERATOR: {
            '0': 'IS'
        }, 

        SPECIAL: {
            '.': 'Empty',
            '#': 'Bound',
        }

    }

    FULLDICT[NOUN] = {k.upper(): v.upper() for k, v in FULLDICT[OBJECT].items()}
    TYPEDICT = {name: key for key, value in FULLDICT.items() for name in value.keys()}
    REBUILD_TEXTURE = False

    @property
    def default_property(self):
        if self.is_object():
            return Property.REGULAR
        if self.is_text():
            return Property.TEXT
        if self.full_name == 'Empty':
            return Property.EMPTY
        if self.full_name == 'Bound':
            return Property.STOP


    # ====== 不重要的历史遗留代码 =======

    def noun2object(self):
        if self.is_noun():
            return Material(self.short_name.lower())   
    
    def object2noun(self):
        if self.is_object():
            return Material(self.short_name.upper())
    
    @classmethod
    def initial_from_data(cls, source_dir='textures', target_dir='texture'):

        base_path = Path(__file__).parent
        source_path, target_path = base_path / source_dir, base_path / target_dir
        target_path.mkdir(exist_ok=True)

        all_entities = [(id, TYPE, full) for TYPE,DICT in cls.FULLDICT.items() for id, full in DICT.items() if TYPE != cls.SPECIAL]
        
        for entity_id, entity_type, full_name in all_entities:
            src_file = source_path / cls.old_texture(entity_id)
            dst_file = target_path / f"en_{entity_type}_{full_name.lower()}.png"
            if src_file.exists(): shutil.copy2(src_file, dst_file)

    if REBUILD_TEXTURE:
        initial_from_data()

    @classmethod
    def old_texture(cls, name):
        new = cls(name)
        if new.type is new.NOUN:
            return f'en_rule_{new.full_name.lower()}.png'
        if new.type is new.OBJECT:
            return f'en_normal_{new.full_name.lower()}.png'
        if new.type is new.PROPERTY:
            return f'en_attribute_{new.full_name.lower()}.png'
        if new.type is new.OPERATOR:
            return f'en_keyword_{new.full_name.lower()}.png'


class Entity:

    def __init__(self, name: str = '.', coord: Union[tuple, 'Coord'] = (0, 0), 
                 global_id: int = None, prop: int = None):

        self.gridmap, self.tile = None, None
        self.global_id = global_id

        self.material = Material(name)
        self.coord = Coord(coord)
        self._prop = Property(self.get_default_property()).union(prop or 0)
        self._dirty = False



    # ====== 上级操作 ======
    def get_tile(self): return self.tile
    def get_gridmap(self): return self.gridmap
    def get_global_id(self): return self.global_id

    # ====== 名称操作 ======
    def get_entity_id(self): return self.material.short_name
    def get_full_name(self): return self.material.full_name
    def is_text(self): return self.material.is_text()
    def get_texture(self): return self.material.texture 
    def get_identity(self): return 'Text' if self.is_text() else self.get_full_name()
    
    def trans_id(self, new_id):
        new = Entity(new_id, self.get_coord()) 
        new.mark_prop_dirty()
        return new
    
    # ====== 坐标操作 ======
    def get_coord(self): return self.coord if not self.tile else self.tile.get_coord()
    def get_x(self): return self.coord.get_x()
    def get_y(self): return self.coord.get_y()
    def set_coord(self, coord): self.coord = coord

    # ====== 属性操作 ======
    @property
    def prop(self):
        if self._dirty:
            self.update_prop()
        return self._prop

    def get_prop(self): return self.prop
    def get_prop_flag(self): return self.prop._flag
    def get_prop_lst(self): return self.prop.prop_lst

    def get_default_property(self): return self.material.default_property
    def mark_prop_dirty(self): 
        self._dirty = True
        if self.tile is not None:
            self.tile.mark_dirty()

    def update_prop(self):
        manager = self.gridmap.get_ruler('np')
        self._prop.update(manager[self.get_entity_id()])
        self._dirty = False

    def add_prop(self, prop): self.prop.add(prop)
    def remove_prop(self, prop): self.prop.remove(prop)
    def has_prop(self, prop): return prop in self.prop
    def clear_prop(self): self.prop.clear()

    # ====== 存储读取 ======
    def quick_save(self, encoding=True):
        saving = (self.get_global_id(), self.get_entity_id(), self.get_prop_flag(), self.get_x(), self.get_y())
        return encoding(saving) if encoding else saving
    
    def quick_save_without_coord(self, to_string=True):
        saving = (self.get_global_id(), self.get_entity_id(), self.get_prop_flag())
        return encoding(saving) if to_string else saving

    @classmethod
    def quick_load(cls, data):
        data = decoding(data) if isinstance(data, str) else data
        global_id, entity_id, flag, x, y = data
        return cls(str(entity_id), Coord((int(x), int(y))), int(global_id), flag)
    
    def get_description(self):
        return f'@{self.get_coord()}: {self.get_full_name()} {self.get_prop_lst()}'
    
    def __str__(self):
        return self.quick_save()
    
    def __repr__(self):
        return self.get_description()
    
    # ===== 相似度计算 ======
    def cal_sim(self, entity, id_weight = 0.4):
        prop_sim = self.prop.cal_sim(entity.prop)
        id_sim = 1.0 if self.get_entity_id() == entity.get_entity_id() else 0.0
        return id_weight * id_sim + (1 - id_weight) * prop_sim
    
    def equal_prop(self, entity): return self.prop == entity.prop
    def equal_id(self, entity): return self.get_entity_id() == entity.get_entity_id()
    def equal_global(self, entity): return self.get_global_id() == entity.get_global_id()
    
    def equal(self, entity):
        return self.equal_prop(entity) and self.equal_id(entity) and self.equal_global(entity)

    def __eq__(self, other):
        return self.equal(other)