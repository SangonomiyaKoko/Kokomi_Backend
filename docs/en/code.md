# Business Error Status Codes

This document defines all business error status codes in the API response.

> These status codes are all returned within **HTTP 200** responses, with the `status` field set to `"ok"`. The specific error type is distinguished by the `code` field.

| Code | Status | Message | Description |
|------|--------|---------|-------------|
| 1001 | ok | NodeNotAvailable | The current node is under maintenance and unavailable |
| 1002 | ok | RegionNotSupported | The current region does not support this API |
| 1003 | ok | UserNotExist | User data does not exist |
| 1004 | ok | ClanNotExist | Clan data does not exist |
| 1005 | ok | UserDataIsNone | User data is empty |
| 1006 | ok | ClanDataIsNone | Clan data is empty |
| 1007 | ok | UserInBlacklist | User is in the blacklist |
| 1008 | ok | ClanInBlacklist | Clan is in the blacklist |
| 1009 | ok | UserHiddenProfile | User has hidden their profile/stats |
| 1010 | ok | AcqurieLockFailed | Failed to acquire write lock |
| 1011 | ok | NoStatisticsData | No statistics data available |
| 1012 | ok | RecentNotEnable | Recent battles feature is not enabled |
| 1013 | ok | UserNotActive | User is in an inactive state |
| 1014 | ok | InvalidAccessToken | Access Token is invalid |
| 1015 | ok | InvalidAuthToken | Auth Token is invalid |
