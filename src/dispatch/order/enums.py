from enum import Enum
class OrderType(str, Enum):
    # There are two jobs, pick and drop. All two jobs should be assigned to a same worker.
    PickDrop = "pickdrop" 
    # Most commonly used, for parcel one off dropoff job, or FSM customer visit.
    Visit = "visit"
    # all jobs must be on same customer site, same time, and be assigned to different worker.
    Shared = "shared"
    # all jobs included must be planned and not moved.
    Appointment = "appt"

class OrderStatus(str, Enum):
    Init = "init" #初始状态
    Sync = "sync" #同步
    Plan = "plan" #排班
    Processing = "processing"  #处理中
    Compete = "compete"  #结束



class BusinessStatus(str, Enum):
    Delivery  = "delivery " #送货

