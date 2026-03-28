"""Stage 1: Data Collection -- сбор данных из внешних источников.

Спека: docs/03-collectors.md.

Четыре агента запускаются параллельно (min_successful=2):
- NewsScout: 100-200 новостных сигналов (RSS + web search)
- EventCalendar: 10-30 запланированных событий на target_date
- OutletHistorian: стилевой и редакционный профиль целевого СМИ
- ForesightCollector: прогнозы из Metaculus, Polymarket, GDELT

Контракт:
    Вход: PipelineContext с outlet + target_date.
    Выход: AgentResult.data = {"signals"|"scheduled_events"|"outlet_profile"|"foresight_*": ...}
"""

from src.agents.collectors.event_calendar import EventCalendar
from src.agents.collectors.foresight_collector import ForesightCollector
from src.agents.collectors.news_scout import NewsScout
from src.agents.collectors.outlet_historian import OutletHistorian

__all__ = ["EventCalendar", "ForesightCollector", "NewsScout", "OutletHistorian"]
