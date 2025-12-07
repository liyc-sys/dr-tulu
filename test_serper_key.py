import sys
import os
import json
import requests

def test_serper():
    # 1. Get API Key
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("Error: SERPER_API_KEY environment variable is not set.")
        print("Please export it before running this script:")
        print("export SERPER_API_KEY='your_key'")
        sys.exit(1)
        
    print(f"Testing Serper API with key: {api_key[:5]}... (masked)")
    
    # 2. Define API parameters (matching logic in agent/dr_agent/mcp_backend/apis/serper_apis.py)
    url = "https://google.serper.dev/search"
    query = "machine learning"
    num_results = 1
    gl = "us"
    hl = "en"
    search_type = "search"
    
    payload = json.dumps({
        "q": query,
        "num": num_results,
        "gl": gl,
        "hl": hl,
        "type": search_type
    })
    
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    
    # 3. Make the request
    print(f"Searching for: '{query}'...")
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        
        if response.status_code != 200:
            print(f"\nError: API request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)
            
        results = response.json()
        
        if results and 'organic' in results and len(results['organic']) > 0:
            print("\nSuccess! Serper API is working.")
            print("-" * 30)
            item = results['organic'][0]
            print(f"Title: {item.get('title')}")
            print(f"Link:  {item.get('link')}")
            print(f"Snippet: {item.get('snippet')}")
            print("-" * 30)
        else:
            print("\nWarning: API returned a response but no organic results found.")
            print("Full Response:", json.dumps(results, indent=2))
            
    except Exception as e:
        print(f"\nError calling Serper API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_serper()

