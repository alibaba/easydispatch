from enum import Enum

class OrganizationType(str, Enum):
    """
    -- DEFAULT: is for all normal organization, registered on market place. It uses only stable features.
    -- POC: In Proof-of-Concept (POC) orgnization, we show all un-stable features for demo purpose.
    -- INTERNAL_5GMAX: Organization started as i_, Internal are managed by internal staff. It might be privately deployed, standalone instance.
    """

    DEFAULT = "default"
    POC = "poc"

    INTERNAL_5GMAX = "i_5gmax"



class UserRoles(str, Enum):
    SYSTEM = "sys"
    WORKER = "Worker"
    PLANNER = "Planner"
    OWNER = "Owner"
    CUSTOMER = "Customer"
    # admin = "Admin"
    Address_API_Admin = "Address API Admin"    
    VRP_API_Admin = "VRP API Admin"
    Address_Normalization_API_Admin = "Address Normalization API Admin"
