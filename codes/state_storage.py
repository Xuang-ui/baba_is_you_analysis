"""统一的状态和动作索引存储管理系统

提供抽象的存储后端接口和索引管理器，支持 Gridmap 的 state_index 和 Interaction 的 action_index。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import threading
import json
from pathlib import Path


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
    
    def __init__(self, filepath: str, auto_save: bool = True):
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


# 全局单例管理器（兼容旧代码的过渡方案）
_gamestate_index_manager: Optional[IndexManager] = None
_target_index_manager: Optional[IndexManager] = None
_plan_index_manager: Optional[IndexManager] = None


def get_state_index_manager() -> IndexManager:
    """获取全局 GameState 索引管理器（懒初始化）"""
    global _gamestate_index_manager
    if _gamestate_index_manager is None:
        _gamestate_index_manager = IndexManager(InMemoryBackend(), name="gamestate_index")
    return _gamestate_index_manager


def get_action_index_manager() -> IndexManager:
    """获取全局 TargetInteraction 索引管理器（懒初始化）"""
    global _target_index_manager
    if _target_index_manager is None:
        _target_index_manager = IndexManager(InMemoryBackend(), name="target_index")
    return _target_index_manager


def get_plan_index_manager() -> IndexManager:
    """获取全局 ActionPlan 索引管理器（懒初始化）"""
    global _plan_index_manager
    if _plan_index_manager is None:
        _plan_index_manager = IndexManager(InMemoryBackend(), name="plan_index")
    return _plan_index_manager


def configure_state_backend(backend: StorageBackend) -> None:
    """配置 GameState 索引的存储后端"""
    global _gamestate_index_manager
    _gamestate_index_manager = IndexManager(backend, name="gamestate_index")


def configure_action_backend(backend: StorageBackend) -> None:
    """配置 TargetInteraction 索引的存储后端"""
    global _target_index_manager
    _target_index_manager = IndexManager(backend, name="target_index")


def configure_plan_backend(backend: StorageBackend) -> None:
    """配置 ActionPlan 索引的存储后端"""
    global _plan_index_manager
    _plan_index_manager = IndexManager(backend, name="plan_index")


def configure_backends(state_backend: StorageBackend, 
                      action_backend: Optional[StorageBackend] = None,
                      plan_backend: Optional[StorageBackend] = None) -> None:
    """同时配置 GameState、TargetInteraction 和 ActionPlan 索引的后端
    
    Args:
        state_backend: GameState 索引后端
        action_backend: TargetInteraction 索引后端，如果为 None 则使用与 state_backend 相同类型的新实例
        plan_backend: ActionPlan 索引后端，如果为 None 则使用与 state_backend 相同类型的新实例
    """
    configure_state_backend(state_backend)
    if action_backend is None:
        action_backend = type(state_backend)()
    configure_action_backend(action_backend)
    if plan_backend is None:
        plan_backend = type(state_backend)()
    configure_plan_backend(plan_backend)


def configure_json_storage(storage_dir: str = './data', 
                          auto_save: bool = True) -> tuple:
    """配置所有 manager 使用 JSON 存储
    
    Args:
        storage_dir: 存储目录路径
        auto_save: 是否在每次修改后自动保存
        
    Returns:
        tuple: (gamestate_backend, target_backend, plan_backend)
    """
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)
    
    gamestate_backend = JSONBackend(storage_path / 'gamestates.json', auto_save=auto_save)
    target_backend = JSONBackend(storage_path / 'targets.json', auto_save=auto_save)
    plan_backend = JSONBackend(storage_path / 'plans.json', auto_save=auto_save)
    
    configure_backends(
        state_backend=gamestate_backend,
        action_backend=target_backend,
        plan_backend=plan_backend
    )
    
    return gamestate_backend, target_backend, plan_backend


def save_all_data() -> None:
    """保存所有后端的数据（如果使用的是 JSONBackend）"""
    for manager in [get_state_index_manager(), 
                    get_action_index_manager(),
                    get_plan_index_manager()]:
        if isinstance(manager.backend, JSONBackend):
            manager.backend.save()
            print(f"Saved {len(manager)} items to {manager.backend.filepath}")


def reload_all_data() -> None:
    """重新加载所有后端的数据（如果使用的是 JSONBackend）"""
    for manager in [get_state_index_manager(), 
                    get_action_index_manager(),
                    get_plan_index_manager()]:
        if isinstance(manager.backend, JSONBackend):
            manager.backend.reload()
            print(f"Reloaded {len(manager)} items from {manager.backend.filepath}")
