
import os
from lib.dune_client import DuneClient

# Force the specific ID we used
os.environ["DUNE_HISTORICAL_TICKS_QUERY_ID"] = "6354552"
os.environ["DUNE_API_KEY"] = "sqxzBWktt066SXmNu4Nn6KQXKMHfJnRs"

client = DuneClient()
params = {
    'start_timestamp': 1763992800,
    'end_timestamp': 1764014400
}

print(f"Executing Query {os.environ['DUNE_HISTORICAL_TICKS_QUERY_ID']}...")
try:
    result = client.execute_query(int(os.environ['DUNE_HISTORICAL_TICKS_QUERY_ID']), params)
    print("Success!")
    
    columns_to_show = [
        "snapshot_time", 
        "fees_usd", 
        "pool_fees_usd_from_inputs", 
        "pool_fees_usd_two_sided",
        "weth_usd"
    ]
    
    if result:
        print(f"\nExample Rows (timestamp: {params['start_timestamp']}):")
        for i, row in enumerate(result[:2]):
            print(f"\n--- Row {i+1} ---")
            for col in columns_to_show:
                if col in row:
                    print(f"{col}: {row[col]}")
                else:
                    print(f"{col}: <MISSING>")
    else:
        print("No results returned.")
except Exception as e:
    print(f"\nFAILURE detected:")
    print(e)
