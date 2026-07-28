# Market data

`market_data.xlsx` contains the OHLC input used by the multi-instrument examples, tests, and charting notebook.

The workbook contains five indices and four US stocks:

- CSI 300, CSI 500, CSI 1000, CSI 2000, and the Wind Micro-cap Index;
- Microsoft, NVIDIA, Alphabet Class A, and Apple.

The backtest engine treats this workbook as raw market data only. Strategy
formulas do not read cached formulas, calculated cells, or spreadsheet row
positions.
