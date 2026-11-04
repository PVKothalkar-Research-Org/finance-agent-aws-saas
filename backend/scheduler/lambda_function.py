"""
Lambda function to trigger the researcher function URL.
Called by EventBridge on a schedule.
"""
from typing import Any
import os
import urllib.request
import json


def handler(event, context) -> dict[str, Any]:
    """Trigger the research endpoint on the researcher function URL."""
    
    researcher_url = os.environ.get('RESEARCHER_URL')
    if not researcher_url:
        raise ValueError("RESEARCHER_URL environment variable not set")
    
    # Remove any protocol if included
    if researcher_url.startswith('https://'):
        researcher_url = researcher_url.replace('https://', '')
    elif researcher_url.startswith('http://'):
        researcher_url = researcher_url.replace('http://', '')
    
    url = f"https://{researcher_url}/research"
    
    try:
        # Create POST request with empty JSON body (agent will pick topic)
        data = json.dumps({}).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data,
            method='POST',
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=180) as response:
            result = response.read().decode('utf-8')
            print(f"Research triggered successfully: {result}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Research triggered successfully',
                    'result': result
                })
            }
    except Exception as e:
        print(f"Error triggering research: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }