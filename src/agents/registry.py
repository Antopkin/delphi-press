"""Реестр агентов — DI-контейнер для инстанциирования и поиска агентов.

Спека: docs/02-agents-core.md (§6).

Контракт:
    AgentRegistry хранит инстансы BaseAgent, доступные по имени.
    Orchestrator получает агентов через registry.get_required(name).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.base import BaseAgent
    from src.llm.router import ModelRouter

logger = logging.getLogger(__name__)


class AgentRegistry:
    """DI-контейнер для агентов пайплайна.

    Хранит инстансы BaseAgent, проиндексированные по agent.name.
    """

    def __init__(self, llm_client: ModelRouter) -> None:
        self._llm_client = llm_client
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Зарегистрировать готовый инстанс агента.

        Raises:
            ValueError: Если агент с таким именем уже зарегистрирован.
        """
        if agent.name in self._agents:
            msg = f"Agent '{agent.name}' is already registered"
            raise ValueError(msg)
        self._agents[agent.name] = agent
        logger.debug("Registered agent '%s'", agent.name)

    def register_class(self, agent_class: type[BaseAgent]) -> None:
        """Инстанциировать класс агента с llm_client и зарегистрировать.

        Raises:
            TypeError: Если класс не является подклассом BaseAgent.
        """
        from src.agents.base import BaseAgent

        if not (isinstance(agent_class, type) and issubclass(agent_class, BaseAgent)):
            msg = f"{agent_class} is not a subclass of BaseAgent"
            raise TypeError(msg)
        agent = agent_class(llm_client=self._llm_client)
        self.register(agent)

    def register_factory(
        self,
        name: str,
        factory: Callable[[ModelRouter], BaseAgent],
    ) -> None:
        """Создать агента через фабричную функцию и зарегистрировать.

        Фабрика получает llm_client и возвращает готовый инстанс.
        Используется для агентов с дополнительными зависимостями (collectors и др.).
        """
        agent = factory(self._llm_client)
        if agent.name != name:
            logger.warning(
                "Factory name '%s' != agent.name '%s', using agent.name", name, agent.name
            )
        self.register(agent)

    def get(self, name: str) -> BaseAgent | None:
        """Получить агента по имени. Возвращает None если не найден."""
        agent = self._agents.get(name)
        if agent is None:
            logger.warning("Agent '%s' not found in registry", name)
        return agent

    def get_required(self, name: str) -> BaseAgent:
        """Получить агента по имени. Raises KeyError если не найден.

        Raises:
            KeyError: С перечислением доступных агентов.
        """
        agent = self._agents.get(name)
        if agent is None:
            available = ", ".join(sorted(self._agents.keys())) or "(empty)"
            msg = f"Agent '{name}' not found. Available: {available}"
            raise KeyError(msg)
        return agent

    def list_agents(self) -> list[str]:
        """Список зарегистрированных имён агентов (отсортированный)."""
        return sorted(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents


def build_default_registry(
    llm_client: ModelRouter,
    *,
    collector_deps: dict | None = None,
) -> AgentRegistry:
    """Создать реестр со всеми 17 агентами пайплайна.

    Args:
        llm_client: ModelRouter для всех агентов.
        collector_deps: Зависимости для коллекторов (rss_fetcher, web_search и др.).
            Если None — коллекторы не регистрируются.

    Агенты для регистрации (17):
    - Collectors: NewsScout, EventCalendar, OutletHistorian
    - Analysts: EventTrendAnalyzer, GeopoliticalAnalyst, EconomicAnalyst, MediaAnalyst
    - Forecasters: RealistAgent, GeostrategistAgent, EconomistAgent,
                   MediaExpertAgent, DevilsAdvocateAgent, MediatorAgent, JudgeAgent
    - Generators: FramingAgent, StyleReplicatorAgent, QualityGateAgent
    """
    registry = AgentRegistry(llm_client)

    if collector_deps is not None:
        from src.agents.collectors.event_calendar import EventCalendar
        from src.agents.collectors.news_scout import NewsScout
        from src.agents.collectors.outlet_historian import OutletHistorian

        registry.register(
            NewsScout(
                llm_client,
                rss_fetcher=collector_deps["rss_fetcher"],
                web_search=collector_deps["web_search"],
                outlet_catalog=collector_deps["outlet_catalog"],
            )
        )
        registry.register(
            EventCalendar(
                llm_client,
                web_search=collector_deps["web_search"],
            )
        )
        registry.register(
            OutletHistorian(
                llm_client,
                scraper=collector_deps["scraper"],
                outlet_catalog=collector_deps["outlet_catalog"],
                profile_cache=collector_deps["profile_cache"],
            )
        )

    return registry
