"""统一的状态和动作索引存储管理系统

提供抽象的存储后端接口和索引管理器，支持 Gridmap 的 state_index 和 Interaction 的 action_index。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import threading
import json
from pathlib import Path


# -------------------------
# StorageBackend - 抽象存储后端
# -------------------------
class StorageBackend(ABC):
    """存储后端的抽象基类"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """获取指定键的值"""
        pass
    
    @abstractmethod
    def put(self, key: str, value: Dict[str, Any]) -> None:
        """存储键值对"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除指定键，返回是否成功"""
        pass
    
    @abstractmethod
    def contains(self, key: str) -> bool:
        """检查键是否存在"""
        pass
    
    @abstractmethod
    def keys(self) -> List[str]:
        """返回所有键的列表"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空所有数据"""
        pass
    
    @abstractmethod
    def __len__(self) -> int:
        """返回存储的条目数量"""
        pass


class InMemoryBackend(StorageBackend):
    """基于内存字典的简单后端实现（线程安全）"""
    
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data.get(key)
    
    def put(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            self._data[key] = value
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._data
    
    def keys(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


class JSONBackend(StorageBackend):
    """基于 JSON 文件的存储后端（线程安全）
    
    每次 put/delete 操作都会自动保存到文件
    """
    
    def __init__(self, filepath: str, auto_save: bool = False):
        """初始化 JSON 后端
        
        Args:
            filepath: JSON 文件路径
            auto_save: 是否在每次修改后自动保存（默认 True）
        """
        self.filepath = Path(filepath)
        self.auto_save = auto_save
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._modified = False
        self._load()
    
    def _load(self) -> None:
        """从文件加载数据"""
        with self._lock:
            if self.filepath.exists():
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        self._data = json.load(f)
                    self._modified = False
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Failed to load {self.filepath}: {e}")
                    self._data = {}
            else:
                self._data = {}
    
    def save(self) -> None:
        """手动保存数据到文件"""
        with self._lock:
            if not self._modified and self.filepath.exists():
                return  # 没有修改且文件存在，跳过保存
            
            # 确保目录存在
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存到临时文件，然后原子性地重命名
            temp_path = self.filepath.with_suffix('.tmp')
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                temp_path.replace(self.filepath)
                self._modified = False
            except Exception as e:
                print(f"Error saving {self.filepath}: {e}")
                if temp_path.exists():
                    temp_path.unlink()
    
    def _auto_save(self) -> None:
        """如果启用了 auto_save，则保存数据"""
        if self.auto_save:
            self.save()
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data.get(key)
    
    def put(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            self._data[key] = value
            self._modified = True
            self._auto_save()
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._modified = True
                self._auto_save()
                return True
            return False
    
    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._data
    
    def keys(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._modified = True
            self._auto_save()
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
    
    def reload(self) -> None:
        """从文件重新加载数据（丢弃未保存的修改）"""
        self._load()


# -------------------------
# IndexManager - 对不同的后端同等的调用
# -------------------------
class IndexManager:
    """统一的索引管理器，封装对后端的访问"""
    
    def __init__(self, backend: StorageBackend, name: str = "index"):
        """
        Args:
            backend: 存储后端实例
            name: 索引名称（用于日志和调试）
        """
        self.backend = backend
        self.name = name
    
    def get(self, key: str, default=None) -> Optional[Dict[str, Any]]:
        """获取指定键的值，如果不存在返回 default"""
        result = self.backend.get(key)
        return result if result is not None else default
    
    def put(self, key: str, value: Dict[str, Any]) -> None:
        """存储键值对"""
        self.backend.put(key, value)
    
    def delete(self, key: str) -> bool:
        """删除指定键"""
        return self.backend.delete(key)
    
    def __contains__(self, key: str) -> bool:
        """支持 'key in manager' 语法"""
        return self.backend.contains(key)
    
    def __getitem__(self, key: str) -> Dict[str, Any]:
        """支持 manager[key] 语法"""
        result = self.backend.get(key)
        if result is None:
            raise KeyError(f"Key '{key}' not found in {self.name}")
        return result
    
    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        """支持 manager[key] = value 语法"""
        self.backend.put(key, value)
    
    def keys(self) -> List[str]:
        """返回所有键"""
        return self.backend.keys()
    
    def clear(self) -> None:
        """清空所有数据"""
        self.backend.clear()
    
    def __len__(self) -> int:
        """返回条目数量"""
        return len(self.backend)
    
    def update(self, mapping: Dict[str, Dict[str, Any]]) -> None:
        """批量更新多个键值对"""
        for key, value in mapping.items():
            self.backend.put(key, value)


# -------------------------
# DataManager - 统一管理三类索引
# -------------------------
class DataManager:
    """统一的数据管理器，管理 GameState、TargetInteraction、ActionPlan 三类索引"""

    _instance: Optional['DataManager'] = None

    def __init__(self, STORAGE_DIR: Optional[str] = None):
        """初始化三个索引管理器"""
        if DataManager._instance is not None:
            raise Exception("DataManager is a singleton! Use get_instance() to get the instance.")
        self._configure_storage(STORAGE_DIR)

    def _configure_storage(self, storage_dir: Optional[str] = None):
        
        if storage_dir is None:
            self.gamestate_manager = IndexManager(InMemoryBackend(), name="gamestate_index")
            self.target_manager = IndexManager(InMemoryBackend(), name="target_index")
            self.plan_manager = IndexManager(InMemoryBackend(), name="plan_index")
            return
        
        storage_path = Path(storage_dir)
        storage_path.mkdir(parents=True, exist_ok=True)
        self.gamestate_manager = IndexManager(JSONBackend(storage_path / 'gamestates.json'), name="gamestate_index")
        self.target_manager = IndexManager(JSONBackend(storage_path / 'targets.json'), name="target_index")
        self.plan_manager = IndexManager(JSONBackend(storage_path / 'plans.json'), name="plan_index")

    @classmethod
    def get_instance(cls) -> 'DataManager':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._configure_storage(None)
        return cls._instance
    
    def configure_storage_dir(self, storage_dir: str, save: bool = False):
        """重新配置存储目录"""
        if save: 
            self.save_all()
        self._configure_storage(storage_dir)

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        cls._instance = None
    
    def save_all(self):
        for manager in [self.gamestate_manager, 
                        self.target_manager,
                        self.plan_manager]:
            if isinstance(manager.backend, JSONBackend):
                manager.backend.save()

    def reload_all(self):
        for manager in [self.gamestate_manager, 
                        self.target_manager,
                        self.plan_manager]:
            if isinstance(manager.backend, JSONBackend):
                manager.backend.reload()
                print(f"Reloaded {len(manager)} items from {manager.backend.filepath}")

    def clear_all(self):
        for manager in [self.gamestate_manager, 
                        self.target_manager,
                        self.plan_manager]:
            manager.clear()
            print(f"Cleared all items from {manager.name}")

    def get_gamestate(self, state_key: str):
        """获取游戏状态摘要"""
        return self.gamestate_manager.get(state_key)
    
    def get_gamestate_ins(self, state_key: str):
        """获取游戏状态摘要的实例形式"""
        from recorder import State
        return State.from_key(state_key)
    
    def set_gamestate(self, state_key: str, state_summary: dict):
        """存储游戏状态摘要"""
        self.gamestate_manager[state_key] = state_summary
    
    def get_target(self, target_key: str):
        """获取目标交互摘要"""
        return self.target_manager.get(target_key)
    
    def get_target_ins(self, target_key: str):
        """获取目标交互摘要的实例形式"""
        from recorder import Interaction
        return Interaction.from_key(target_key)
    
    def set_target(self, target_key: str, target_summary: dict):
        """存储目标交互摘要"""
        self.target_manager[target_key] = target_summary
    
    def get_plan(self, plan_key: str):
        """获取动作计划"""
        return self.plan_manager.get(plan_key)
    
    def set_plan(self, plan_key: str, plan_data: dict):
        """存储动作计划"""
        self.plan_manager.put(plan_key, plan_data)
    
    
    def __repr__(self):
        return (f"DataManager(gamestates={len(self.gamestate_manager.keys())}, "
                f"targets={len(self.target_manager.keys())}, "
                f"plans={len(self.plan_manager)})")


def get_data_manager(storage_dir: Optional[str] = None, save: bool = False) -> DataManager:
    """获取全局数据管理器实例"""
    dm = DataManager.get_instance()
    if storage_dir is not None:
        dm.configure_storage_dir(storage_dir, save)
    return dm


if __name__ == "__main__":
    # 简单测试
    from recorder import State
    dm = get_data_manager('./recording/tutorial')
    unit_post = set([dm.get_plan(p)['post_state'] for p in dm.plan_manager.keys() if p.startswith('Unit_')])
    for i, key in enumerate(unit_post):
        if (i + 1) % 10 == 0: print(i + 1)
        State.from_key(key)
        
    print(len(unit_post))