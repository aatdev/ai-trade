---
name: TradingView Chart Setup — Active Indicators
description: Список активных индикаторов на чарте пользователя и особенности форматирования тикеров
type: reference
---

## Активные индикаторы на дневном чарте (entity IDs сессионные, не кешируются)

- Moving Average Exponential (3 штуки — разные периоды, текущие значения: ~33.53, ~39.05, ~41.56 для ENPH)
- Bollinger Bands (Basis, Upper, Lower)
- Volume
- Volume Delta
- Relative Strength Index (RSI)
- Stochastic (%K, %D)
- Trading Sessions (2 экземпляра)
- Niveles de Opciones (кастомный Pine — уровни опционов)
- Liquidation HeatMap [BigBeluga]
- Average True Range Overlay
- All Chart Patterns (кастомный Pine — автопаттерны)
- Session Volume Profile HD
- Visible Range Volume Profile
- Open Interest
- Liquidations

## Форматы тикеров

- NASDAQ акции: "NASDAQ:ENPH", "NASDAQ:AAPL" — работает надёжно
- NYSE акции: "NYSE:ticker"
- MOEX: "MOEX:ticker"

## Особенности

- RSI доступен через data_get_study_values без фильтрации
- Stochastic возвращает %K и %D
- Три EMA — разные периоды, значения разные; период неизвестен (определяется из chart_get_state по entity ID, но он сессионный)
- Pine-индикаторы (Niveles de Opciones, All Chart Patterns) — данные через data_get_pine_lines / data_get_pine_labels
- data_get_pine_lines вернул 0 результатов для ENPH — возможно, кастомные индикаторы не рисуют линии для этого тикера
