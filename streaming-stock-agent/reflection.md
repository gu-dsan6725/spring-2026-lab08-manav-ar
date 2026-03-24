## Reflection

### 1. How did the LLM know to call your new tool?

The LLM selects tools based on the description field in the tool schema. When the user says "Compare AAPL and MSFT," the model matches the intent against all available tool descriptions and finds that compare_stocks described as comparing two stocks side-by-side is the best fit. The description acts as a semantic routing signal, the clearer and more specific it is, the more reliably the model picks the right tool.

### 2. What happens if the tool schema description is unclear?

If the description is vague (e.g., just "A stock tool"), the LLM may pick the wrong tool or not use the new tool at all. For example, it might call get_stock_price twice instead of compare_stocks , since it cannot distinguish between them based on a poor description. It could also hallucinate parameters or refuse to call the tool entirely. Good descriptions should include when to use the tool and what kind of user intent triggers it.

### 3. How does the agent decide between compare_stocks and get_stock_price ?

The agent examines the user's intent and matches it against each tool's description. If the user mentions two stocks and uses comparison language ("compare," "vs," "which is better"), the agent routes to compare_stocks because its description explicitly mentions side-by-side comparison. If the user asks about a single stock's price, get_stock_price is the better match. The parameter schemas also guide the decision compare_stocks expects two symbols, while get_stock_price expects one ticker, which aligns with the structure of each respective query.

### 4. How would you add validation for parameter values?

You could validate inside the _compare_stocks() function by checking that both symbols are non-empty strings containing only uppercase letters, and that they are different from each other. For example, reject symbols shorter than 1 character or longer than 5, and return an error dict if the yfinance lookup returns no price data. You could also add an enum or pattern field in the JSON Schema to constrain valid inputs at the schema level, though in practice runtime validation with clear error messages is more robust.

### 5. What if the user asks to compare 3 stocks instead of 2?

The current compare_stocks tool only accepts two symbols, so the agent would need to either call it multiple times (AAPL vs MSFT, AAPL vs GOOGL, MSFT vs GOOGL) or fall back to calling get_stock_price three times and synthesizing the comparison in its response text. A better long-term solution would be to create a new tool (e.g., compare_multiple_stocks ) that accepts a list of symbols, or to modify the existing tool s schema to accept an array instead of two fixed parameters. The LLM is generally good at working around tool limitations by chaining multiple calls, but a purpose-built tool would produce cleaner results.

