# API Return Value Specification

## Overview

All API endpoints use a unified JSON response format, distinguishing response type and status via the `status` and `code` fields.

### HTTP Status Code Overview

| HTTP Status Code | Description | Response Format |
|-----------------|-------------|-----------------|
| **200 OK** | Request processed successfully; business result determined by the `code` field in the response body | Standard business JSON format |
| **403 Forbidden** | Invalid token or insufficient permissions | / |
| **422 Unprocessable Entity** | Request parameter validation failed, e.g. missing required fields, malformed input | / |
| **500 Internal Server Error** | Internal server exception, typically an uncaught system-level error | / |

> **Core Design Principle:**
> - Normal business logic processing (including business errors such as user not found, node unavailable, etc.) all return **HTTP 200**. Business success/failure is distinguished by the `code` field in the response body.
> - Only request-level errors (authentication failure, parameter validation failure) or system-level exceptions return a non-200 HTTP status code.

## Standard Business Response Structure (HTTP 200)

### Type Definitions

```typescript
// Base response structure
interface BaseResponse {
    status: 'ok' | 'error';  // Response status
    code: number;             // Business status code
    message: string;          // Response message
}

// Success response (code: 1000)
interface SuccessResponse<T = any> extends BaseResponse {
    status: 'ok';
    code: 1000;
    message: 'Success';
    data: T | null;           // Business data
}

// API call failure response (code: 2000)
interface APIFailedResponse extends BaseResponse {
    status: 'error';
    code: 2000;
    message: 'APIFailed';
    data: {
        node_info: string;    // Node info / region identifier
        error_name: string;   // Error name
    };
}

// Error response (code: 3000)
interface ErrorResponse extends BaseResponse {
    status: 'error';
    code: 3000;
    message: string;
    error: {
        trace_id: string;     // Trace ID (UUID) for log correlation
        node_info: string;    // Node info / region identifier
        error_name: string;   // Error name
    };
}
```

---

## Status Code Reference

### Success Status Code (Code 1000)

| Code | Status | Message | Description |
|------|--------|---------|-------------|
| 1000 | ok | Success | Data retrieved successfully or operation completed |

### API Call Failure Status Code (Code 2000)

| Code | Status | Message | Description |
|------|--------|---------|-------------|
| 2000 | error | APIFailed | Request to the game API failed, typically due to network issues |

### Exception Error Status Code (Code 3000)

| Code | Status | Message | Description |
|------|--------|---------|-------------|
| 3000 | error | Variable | General exception error; see `message` and `error.error_name` fields for details |

### Business Error Status Codes (1001-1015)

> 📖 For detailed status code descriptions, response examples, and client-side handling guidelines, see [Business Error Status Codes](./code.md)

---

## Response Examples

### HTTP 200 - Business Responses

#### 1. Success Response

```json
{
    "status": "ok",
    "code": 1000,
    "message": "Success",
    "data": {
        "user_id": "12345",
        "username": "player1"
    }
}
```

> code=1000 does not necessarily mean `data` carries business data. For some endpoints, code=1000 indicates a successful operation or refresh, and `data` may be null.

#### 2. ⚠️ Server Maintenance Response

> When `code === 1001` is detected, the node server is under maintenance.

```json
{
    "status": "ok",
    "code": 1001,
    "message": "NodeNotAvailable"
}
```

#### 3. Predefined Business Error Response

> Indicates that business data could not be retrieved due to the given reason (e.g. user does not exist or has hidden their profile).

```json
{
    "status": "ok",
    "code": 1003,
    "message": "UserNotExist"
}
```

#### 4. Exception Error Response

> You can use the `node_info` + `trace_id` parameters to locate the corresponding error log for debugging.

```json
{
    "status": "error",
    "code": 3000,
    "message": "DatabaseError",
    "error": {
        "trace_id": "550e8400-e29b-41d4-a716-446655440000",
        "node_info": "cn",
        "error_name": "DatabaseConnectionError"
    }
}
```

#### 5. Game API Call Failure Response

> Caused by network instability.

```json
{
    "status": "error",
    "code": 2000,
    "message": "APIFailed",
    "data": {
        "node_info": "cn",
        "error_name": "GameAPITimeout"
    }
}
```

---

## Business Data Structure

### BasicResponse

When `code === 1000`, this is the common data structure carried in the `data` field for statistics-type endpoints:

```python
@dataclass
class BasicResponse:
    """Basic response data structure for data endpoints"""
    mode: str = ''           # Data mode (pve/pvp/rank/...)
    type: str = ''           # Data type (solo/div2/div3/...)
    basic: Dict[str, Any]    # Basic info of the user or clan
    statistics: Dict[str, Any]   # Actual statistics data
```

Corresponding JSON structure:

```json
{
    "mode": "pvp",
    "type": "solo",
    "basic": {
        "account_id": "12345",
        "nickname": "player1"
    },
    "statistics": {
        "battles": 100,
        "wins": 60
    }
}
```

---

## Client-Side Processing Flow

- **HTTP non-200**: Request-level error, handle separately
- **HTTP 200 + code === 1000**: Success, return `(false, data)`
- **HTTP 200 + code !== 1000**: Business failure, return `(true, full response body)`

### TypeScript Implementation Example

```typescript
interface APIResponse {
    status: 'ok' | 'error';
    code: number;
    message: string;
    data?: any;
    error?: any;
}

async function callAPI<T>(
    url: string, 
    options?: RequestInit
): Promise<T> {
    const response = await fetch(url, options);
    
    // Handle non-200 HTTP status codes
    if (!response.ok) {
        throw new Error(`Request failed: HTTP ${response.status}`);
    }
    
    // Handle HTTP 200 business response
    const result: APIResponse = await response.json();
    
    if (result.code === 1000) {
        return result.data as T;
    }
    
    if (result.code === 1001) {
        throw new Error('Server under maintenance, please try again later');
    }

    // TODO: Handle other possible return values
    
    throw new Error(`Business error: ${result.message}`);
}

// Usage example
try {
    const userData = await callAPI('/api/user/info', {
        method: 'POST',
        headers: {
            'Access-Token': token,
            'Content-Type': 'application/json'
        }
    });
    console.log('User data:', userData);
} catch (error) {
    console.error('Call failed:', error.message);
}
```

### Python Implementation Example

```python
import requests
from typing import Any


def extract_data(response: dict) -> tuple[bool, Any]:
    """Extract data from response
    
    Determines success/failure via the code field:
    - code != 1000: treated as failure, returns (True, full response body)
    - code == 1000: treated as success, returns (False, data field of response)
    """
    if response['code'] != 1000:
        return True, response
    return False, response['data']


def call_api(url: str, token: str, payload: dict = None) -> Any:
    """Generic API call function"""
    headers = {
        'Access-Token': token,
        'Content-Type': 'application/json'
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    # Handle non-200 HTTP status codes
    if response.status_code != 200:
        raise Exception(f'Request failed: HTTP {response.status_code}')
    
    result = response.json()
    is_error, data = extract_data(result)
    
    if is_error:
        code = result['code']
        if code == 1001:
            raise Exception('Server under maintenance, please try again later')
        # TODO: Handle other possible return values
        raise Exception(f'Business error [{code}]: {result["message"]}')
    
    return data


# Usage example
try:
    user_data = call_api('/api/user/info', token='your-access-token')
    print('User data:', user_data)
except Exception as e:
    print('Call failed:', str(e))
```
