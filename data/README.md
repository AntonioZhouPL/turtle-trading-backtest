# Market data

`market_data.xlsx` contains the OHLC input used by the multi-instrument examples, tests, and charting notebook.

The workbook contains five indices and four US stocks:

- CSI 300, CSI 500, CSI 1000, CSI 2000, and the Wind Micro-cap Index;
- Microsoft, NVIDIA, Alphabet Class A, and Apple.

The optional original Excel parity workbook is intentionally not committed because of its size. To run the cell-by-cell parity test, place it at:

```text
data/reference_workbook.xlsx
```

Without that optional file, `test_parity` reports a skip rather than a failure.
