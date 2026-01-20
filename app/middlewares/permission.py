from app.core import EnvConfig, split_config

class IPAccessListManager:
    def is_blacklisted(host: str) -> bool:
        if host in split_config(EnvConfig.get_config().IP_BLACLIST):
            return True
        else:
            return False
        
class UserAccessListManager:
    def is_blacklisted(account_id: int) -> bool:
        if account_id in split_config(EnvConfig.get_config().USER_BLACLIST):
            return True
        else:
            return False
    
class ClanAccessListManager:
    def is_blacklisted(clan_id: int) -> bool:
        if clan_id in split_config(EnvConfig.get_config().CLAN_BLACLIST):
            return True
        else:
            return False