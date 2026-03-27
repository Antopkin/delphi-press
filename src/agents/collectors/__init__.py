"""Stage 1: Data Collection — сбор данных из внешних источников.

Спека: docs/03-collectors.md.

Три агента запускаются параллельно (min_successful=2):
- NewsScout: 100-200 новостных сигналов (RSS + web search)
- EventCalendar: 10-30 запланированных событий на target_date
- OutletHistorian: стилевой и редакционный профиль целевого СМИ

Контракт:
    Вход: PipelineContext с outlet + target_date.
    Выход: AgentResult.data = {"signals"|"scheduled_events"|"outlet_profile": ...}
"""

from src.agents.collectors.event_calendar import EventCalendar
from src.agents.collectors.news_scout import NewsScout
from src.agents.collectors.outlet_historian import OutletHistorian

__all__ = ["EventCalendar", "NewsScout", "OutletHistorian"]
