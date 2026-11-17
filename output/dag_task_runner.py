import asyncio
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set, Union


class CycleDetectedError(Exception):
    pass


class TaskResult:
    def __init__(self, name: str, status: str, duration: float, attempts: int, error: Optional[Exception] = None):
        self.name = name
        self.status = status
        self.duration = duration
        self.attempts = attempts
        self.error = error


class DAGTaskRunner:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._tasks: Dict[str, Any] = {}
        self._deps: Dict[str, List[str]] = {}

    def add_task(self, task_name: str, dependencies: List[str], coroutine_or_factory: Any):
        self._tasks[task_name] = coroutine_or_factory
        self._deps[task_name] = list(dependencies)

    def _topological_order(self) -> List[str]:
        indegree = {name: 0 for name in self._tasks}
        for name, deps in self._deps.items():
            indegree[name] = len(deps)

        queue = deque(name for name in self._tasks if indegree[name] == 0)
        order = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for name, deps in self._deps.items():
                if current in deps:
                    indegree[name] -= 1
                    if indegree[name] == 0:
                        queue.append(name)

        if len(order) != len(self._tasks):
            raise CycleDetectedError("cycle detected in dependency graph")
        return order

    async def _run_task(self, name: str, task_obj: Any) -> TaskResult:
        start = asyncio.get_event_loop().time()
        last_error = None
        attempts = 0
        for attempt in range(self.max_retries + 1):
            attempts += 1
            try:
                coro = task_obj() if callable(task_obj) else task_obj
                await coro
                return TaskResult(name, "success", asyncio.get_event_loop().time() - start, attempts)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    continue
                return TaskResult(name, "failed", asyncio.get_event_loop().time() - start, attempts, last_error)
        return TaskResult(name, "failed", asyncio.get_event_loop().time() - start, attempts, last_error)

    async def run_dag(self) -> Dict[str, TaskResult]:
        order = self._topological_order()
        results: Dict[str, TaskResult] = {}
        for name in order:
            task_obj = self._tasks[name]
            res = await self._run_task(name, task_obj)
            results[name] = res
        return results


def add_task(runner: DAGTaskRunner, task_name: str, dependencies: List[str], coroutine: Any):
    runner.add_task(task_name, dependencies, coroutine)


def run_dag(runner: DAGTaskRunner) -> Dict[str, TaskResult]:
    return asyncio.run(runner.run_dag())


def selftest():
    async def slow_task(delay):
        await asyncio.sleep(delay)

    async def failing_task():
        await asyncio.sleep(0.001)
        raise RuntimeError("task failed")

    async def main():
        runner = DAGTaskRunner(max_retries=2)

        add_task(runner, "a", [], slow_task(0.01))
        add_task(runner, "b", ["a"], slow_task(0.01))
        add_task(runner, "c", ["b"], slow_task(0.01))
        add_task(runner, "d", ["a"], slow_task(0.01))
        add_task(runner, "e", ["c", "d"], slow_task(0.01))

        results = await runner.run_dag()

        # Valid topological sort assertions
        order_list = [r.name for r in results.values()]
        assert set(order_list) == {"a", "b", "c", "d", "e"}
        assert order_list.index("a") < order_list.index("b")
        assert order_list.index("a") < order_list.index("d")
        assert order_list.index("b") < order_list.index("c")
        assert order_list.index("c") < order_list.index("e")
        assert order_list.index("d") < order_list.index("e")

        for key in ["a", "b", "c", "d", "e"]:
            assert results[key].status == "success"
            assert results[key].attempts == 1

        async def cyclic():
            return None

        cyclic_runner = DAGTaskRunner(max_retries=1)
        add_task(cyclic_runner, "x", ["y"], cyclic)
        add_task(cyclic_runner, "y", ["x"], cyclic)
        try:
            await cyclic_runner.run_dag()
            raise AssertionError("cycle detection failed")
        except CycleDetectedError:
            pass

        return True

    return asyncio.run(main())


if __name__ == "__main__":
    selftest()
    print("SELFTEST OK")
