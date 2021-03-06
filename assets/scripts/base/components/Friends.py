import KBEngine
import Functor
from KBEDebug import *
import d_game
import time
from Poller import *
from GlobalDefine import *
from ComFunc import *

class Friends(KBEngine.EntityComponent):
    def __init__(self):
        KBEngine.EntityComponent.__init__(self)
        
    def onAttached(self, owner):
        #DEBUG_MSG("Friends::onAttached(): owner=%i" % (owner.id))
        self.CheckYaoEndTime(int(time.time()))

    def onDetached(self, owner):
        #DEBUG_MSG("Friends::onDetached(): owner=%i" % (owner.id))
        pass

    #客户端断线重连会触发该函数
    def onClientEnabled(self):
        """
        KBEngine method.
        该entity被正式激活为可使用， 此时entity已经建立了client对应实体， 可以在此创建它的
        cell部分。
        """
        DEBUG_MSG("Friends[%i]::onClientEnabled:entities enable." % (self.ownerID))
        self.SetFriendStatus(True, self.owner.databaseID)
        #检查倒计时    
        self.addTimer(0.5,1,TIMER_CD_LAND_5)
        self.TimerIDFriend = self.addTimer(0.5,8,TIMER_CD_FRIEND_DATA_7)
        self.FriendState = 0
        self.InitClientData()

    def InitClientData(self):
        if hasattr(self,'client') and self.client:
            self.reqYaoShuStatus()
            self.reqAllSysMessage('普通消息')
            self.reqAllSysMessage('消费记录')
            self.reqAllSysMessage('邮箱奖励')

    #客户端断线
    def onClientDeath(self):
        """
		KBEngine method.
		客户端对应实体已经销毁
        """
        DEBUG_MSG("Friends[%s].onClientDeath:" % str(self.owner) )
        self.SetFriendStatus(False, self.owner.databaseID)
        
        	
    #设置好友在线状态
    #KBEngine.baseAppData["avatar_玩家的dbid"] = 玩家的entitycall
    def SetFriendStatus(self, status, databaseID):
        if status:
            KBEngine.baseAppData[databaseID] = self.owner
        else:
            del KBEngine.baseAppData[databaseID]
        DEBUG_MSG("Friends baseAppData(dbID:%i,status:%i)" % (databaseID,status) )

    def GetFriendEntity(self, dbid):
        if KBEngine.baseAppData.has_key(dbid):
            return KBEngine.baseAppData[dbid]
        else:
            return None

    def onTimer(self, id, userArg):
        """
		KBEngine method.
		使用addTimer后， 当时间到达则该接口被调用
		@param id		: addTimer 的返回值ID
		@param userArg	: addTimer 最后一个参数所给入的数据
        """
        if userArg == TIMER_CD_LAND_5:
            self.CheckYaoEndTime(int(time.time()))
            self.CheckMessageTime()
        if userArg == TIMER_CD_FRIEND_DATA_7:
            if not self.owner.IsYK():
                self.owner.poller.GetFriendList(self.owner.AccountName(), self.InitFriendList)
       
    def Component(self,name):
        return self.owner.getComponent(name)

    def GetGenerator(self,TypeName):
        return self.owner.generatorFac.GetGenerator(TypeName)

    def BuildGenerator(self,TypeName):
        if self.owner is not None:
            self.owner.generatorFac.BuildGenerator(TypeName)

    """
    ======================================================================================
	系统消息
    """
    def GetConfigSysMessage(self, MessageID):
        try:
            Info = d_game.sysmessage[MessageID]
        except (IndexError, KeyError) as e:
            ERROR_MSG("GetConfigSysMessage error:%s, MessageID:%i" % (str(e), MessageID))
            return None
        return Info

    #消息系统
    def SYSMessage(self, DBID, MessageID, Time, *arg):
        d_sysmessage = self.GetConfigSysMessage(MessageID)
        if d_sysmessage is None:
            return
        MessageType = d_sysmessage['Type']
        MesaageUUID = KBEngine.genUUID64()
        MessageInfo = {'MesaageUUID':MesaageUUID, 'time':Time ,'MessageID':MessageID, 'Endtime':0}
        MessageInfo['ArgList'] = ''
        for argValue in arg:
            Value = ''
            if isinstance(argValue, str):
                Value = argValue
            else:
                Value = str(argValue)
            AddSplitStr(MessageInfo,'ArgList',Value)
        if DBID == 0:
            self.WriteSysMessage(MessageInfo,MessageType)
        else:
            Entity = self.GetFriendEntity(DBID)
            #在线
            if Entity is not None:
                Friends = Entity.getComponent("Friends")
                Friends.WriteSysMessage(MessageInfo,MessageType)
            else: #离线
                self.BuildGenerator('onFriendSysMessage')
                KBEngine.createEntityFromDBID("Account",DBID,Functor.Functor(self.onFriendSysMessage,MessageInfo,MessageType))
                
			
    def onFriendSysMessage(self,MessageInfo,MessageType,baseRef,databaseID,wasActive):
        if baseRef is None:
            DEBUG_MSG("onFriendSysMessage baseRef error:%i" % databaseID)
            if self.owner is not None:
                self.GetGenerator('onFriendSysMessage').Set(databaseID,self.onFriendSysMessage,MessageInfo,MessageType)
        else:
            Friends = baseRef.getComponent("Friends")
            Friends.WriteSysMessage(MessageInfo,MessageType)
            if not wasActive:
                baseRef.destroy()

    def GetMessageTypeNum(self, MessageType):
        num = 0
        minTime = int(time.time() )
        minIndex = 0
        for Index,Message in enumerate(self.SysMessage):
            d_sysmessage = self.GetConfigSysMessage(Message['MessageID'])
            if d_sysmessage is not None and d_sysmessage['Type'] == MessageType:
                if minTime > Message['time']:
                    minTime = Message['time']
                    minIndex = Index
                num += 1
        return num, minTime, minIndex

    #写入消息，每个类型不能超过30条
    def WriteSysMessage(self, MessageInfo, MessageType):
        num, minTime, minIndex = self.GetMessageTypeNum(MessageType)
        if num >= 30:
            del self.SysMessage[minIndex]
        if self.FilterSysMessage(MessageInfo):
            return
        self.SysMessage.append(MessageInfo)
        self.SetMessageRead(MessageType,1)
        if hasattr(self,'client') and self.client:
            self.client.onSysMessage(MessageInfo)
        INFO_MSG("WriteSysMessage:%s" % str(MessageInfo) )

    #过滤消息（邀请偷树消息）
    def FilterSysMessage(self, MessageInfo):
        if MessageInfo['MessageID'] != 3005 and MessageInfo['MessageID'] != 3006:
            return False
        for Message in self.SysMessage:
            if Message['MessageID'] == 3005:
                MessageDBID = GetSplitStr(Message['ArgList'],0)
                MessageInfoDBID = GetSplitStr(MessageInfo['ArgList'],0)
                messagetime = int(GetSplitStr(MessageInfo['ArgList'],2))
                state = GetSplitStr(MessageInfo['ArgList'],-1)
                if (Message['ArgList'] != '' and 
                    state == '0' and                                       #未处理
                    MessageDBID == MessageInfoDBID and                     #邀请人相同
                    int(time.time()) < messagetime ):                      #时间未过期
                    DEBUG_MSG("FilterSysMessage 3005:%s" % str(Message) )
                    return True
            elif Message['MessageID'] == 3006:
                MessageDBID = GetSplitStr(Message['ArgList'],0)
                MessageInfoDBID = GetSplitStr(MessageInfo['ArgList'],0)
                MessagebyDBID = int(GetSplitStr(Message['ArgList'],3))
                MessageInfobyDBID = int(GetSplitStr(MessageInfo['ArgList'],3))
                state = GetSplitStr(MessageInfo['ArgList'],-1)
                if (Message['ArgList'] != '' and 
                    state == '0' and                                        #未处理
                    MessageDBID == MessageInfoDBID and                      #邀请人相同
                    MessagebyDBID == MessageInfobyDBID):                    #被邀请人相同
                    DEBUG_MSG("FilterSysMessage 3006:%s" % str(Message) )    
                    return True
        return False

    #清空消息
    def ClearMessage(self, MessageType):
        for Index,Message in enumerate(self.SysMessage):
            d_sysmessage = self.GetConfigSysMessage(Message['MessageID'])
            if d_sysmessage is None:
                continue
            if d_sysmessage['Type'] == MessageType:
                del self.SysMessage[Index] 

    #修改消息状态
    def ChangeMessageState(self, MesaageUUID, State):
        if MesaageUUID == 0:
            return
        for Message in self.SysMessage:
            if Message['MesaageUUID'] == MesaageUUID:
                if Message['ArgList'] != '':
                    ChangeSplitStr(Message,'ArgList',-1,str(State))
                    if hasattr(self,'client') and self.client:
                        self.client.onSysMessage(Message)
                DEBUG_MSG("ChangeMessageState:%s" % (str(Message)) )

    #请求信息列表
    def reqAllSysMessage(self, MessageType):
        MessageList1 = []
        MessageList2 = []
        Count = 0
        for Message in self.SysMessage:
            d_sysmessage = self.GetConfigSysMessage(Message['MessageID'])
            if d_sysmessage is not None and d_sysmessage['Type'] == MessageType:
                if Count < 15:
                    MessageList1.append(Message)
                    Count += 1
                else:
                    MessageList2.append(Message)

        if MessageList1:
            self.client.onAllSysMessage(MessageType,MessageList1)
            if MessageList2:
                self.client.onAllSysMessage(MessageType,MessageList2)
        else:
            self.client.onAllSysMessage(MessageType,[{'MesaageUUID':0, 'time':0 ,'MessageID':0,'Endtime':0,'ArgList':''}])
        self.client.onReadMessage(self.NoReadNum1,self.NoReadNum2,self.NoReadNum3)
        DEBUG_MSG("reqAllSysMessage MessageList1:%s,%s" % (MessageType,str(MessageList1) ) )
        DEBUG_MSG("reqAllSysMessage MessageList2:%s,%s" % (MessageType,str(MessageList2) ) )

    def reqReadMessage(self, MessageType):
        self.SetMessageRead(MessageType,0)
       
    def SetMessageRead(self, MessageType, NoReadNum):
        if self.NoReadNum1+self.NoReadNum2+self.NoReadNum3 < 90:
            if MessageType == '普通消息':
                self.NoReadNum1 = 0 if NoReadNum == 0 else self.NoReadNum1+NoReadNum
            if MessageType == '消费记录':
                self.NoReadNum2 = 0 if NoReadNum == 0 else self.NoReadNum2+NoReadNum
            if MessageType == '邮箱奖励':
                self.NoReadNum3 = 0 if NoReadNum == 0 else self.NoReadNum3+NoReadNum
        if  hasattr(self,'client') and self.client:
                self.client.onReadMessage(self.NoReadNum1,self.NoReadNum2,self.NoReadNum3)

    def FindMessageByUUID(self,MesaageUUID):
        for index,Message in enumerate(self.SysMessage):
            if Message['MesaageUUID'] == MesaageUUID:
                return index,Message
        return 0,None

    #领奖
    def reqMessageAward(self, MesaageUUID):
        index,Message = self.FindMessageByUUID(MesaageUUID)
        if Message:
            List = Message['ArgList'].split('$')
            List.pop()
            DEBUG_MSG("reqMessageAward List:%s" % str(List) )
            for idx,info in enumerate(List):
                if (idx+1)%2 != 0:
                    awardType = int(info)
                else:
                    awardValue = int(info)
                    self.Component("bags").AddItem(awardType, awardValue, '邮箱领奖' )
                    DEBUG_MSG("reqMessageAward:%i,%i" % (awardType, awardValue) )
            self.client.onMessageAward('成功', MesaageUUID)
            del self.SysMessage[index]
        else:
            ERROR_MSG('MesaageUUID is error')

    #检测消息时间
    def CheckMessageTime(self):
        nowtime = int(time.time())
        for index,Message in enumerate(self.SysMessage):
            if Message['Endtime'] != 0 and nowtime > Message['Endtime']:
                DEBUG_MSG("delete message:%s" % str(Message) )
                del self.SysMessage[index]
                
    """
    ===========================================================================================
	好友列表
    """
    def sqlcallback(self,CurCount,MaxCount,result, rows, insertid, error):
        if len(result) > 0:
            uid = bytes.decode(result[0][0])
            DBID = bytes.decode(result[0][1])
            Name = bytes.decode(result[0][2])
            Icon = bytes.decode(result[0][3])
            gender = bytes.decode(result[0][4])
            friend_info = {'uid':uid, 'DBID':int(DBID) ,'online':0,'Name':Name, 'Icon':int(Icon),'gender':int(gender),'CanSteal':0,'Accept':0}
            if int(DBID) != self.owner.databaseID:
                self.FriendList.append(friend_info)
        if CurCount >= MaxCount:
            if len(self.FriendList) == 0:
                self.OpenFriendList('没有好友')
                self.FriendState = 3
            else:
                self.reqFriendList()
                self.reqYaoShuStatus()
                self.FriendState = 2  
                self.OpenFriendList('成功')
                DEBUG_MSG("FriendList 从数据库加载完毕! %d,%d " % (CurCount, MaxCount))

               
    def	InitFriendList(self, Result):
        if Result is None:
            self.FriendState = 4
            return
        #删除定时器
        self.delTimer(self.TimerIDFriend)
        if Result['status'] == 1:
            self.FriendState = 1
            self.FriendList = []
            CurCount = 0
            for k,v in enumerate(Result['content']):
                CurCount += 1
                sql = """select accountName,entityDBID,sm_Data_name,sm_Data_Icon,sm_Data_gender  
                from kbe_accountinfos,tbl_Account where accountName ='""" + v['uid_friend'] + "' and entityDBID = id;"
                KBEngine.executeRawDatabaseCommand(sql, Functor.Functor(self.sqlcallback,CurCount,len(Result['content'])))        
        else:
            INFO_MSG("获得好友列表失败 error:%s" % ( Result['error']))
            self.FriendState = 3
            self.OpenFriendList('没有好友')

    def GetClientFriendList(self, FriendList):
        for FriendInfo in FriendList:
            #在线
            FriendEntity = self.GetFriendEntity(FriendInfo['DBID'])
            if FriendEntity is not None:
                FriendInfo['online'] = 1
            else:
                FriendInfo['online'] = 0
            #是否接受摇树邀请
            if self.IsExistPlayer(FriendInfo['DBID']):
                FriendInfo['Accept'] = 1
            else:
                FriendInfo['Accept'] = 0

    def reqOpenFriendList(self):
        if self.FriendState == 2:
            self.CheckFriendCanSteal()
            self.OpenFriendList('成功')
        elif self.FriendState == 3:
            self.OpenFriendList('没有好友')
        DEBUG_MSG("reqOpenFriendList state:%d" % (self.FriendState))

    def	reqFriendList(self):
        self.GetClientFriendList(self.FriendList)
        if hasattr(self,'client') and self.client:
            self.client.onFriendList(self.FriendList)  
            DEBUG_MSG("reqFriendList num:%d, FriendList:%s" % (len(self.FriendList), str(self.FriendList) ) )

    def OpenFriendList(self, Msg):
        if hasattr(self,'client') and self.client:
            self.client.onOpenFriendList(Msg)

    def getFrendInfo(self, UID):
        for value in self.FriendList:
            if value['uid'] == UID:
                return value
        return None	
    
    def ChangeFriendInfo(self, ByDBID, key, value):
        for FriendInfo in self.FriendList:
            if FriendInfo['DBID'] == ByDBID:
                FriendInfo[key] = value
                DEBUG_MSG("ChangeFriendSteal :%d,%s,%d" % (ByDBID, key, value) )

    #获得摇树配置
    def GetConfigYaoShu(self, ItemType):
        try:
            Info = d_game.YaoShu[ItemType]
        except (IndexError, KeyError) as e:
            ERROR_MSG("GetConfigYaoShu error:%s, ItemType:%i" % (str(e), ItemType))
            return None
        return Info

    def GetYaoShuPlayerNum(self):
        PlayerNum = 0
        for ApplyInfo in self.ApplyList:
            if ApplyInfo['IsYao'] == 1:
                PlayerNum += 1
        return PlayerNum

    def IsExistPlayer(self, DBID):
        for ApplyInfo in self.ApplyList:
            if ApplyInfo['DBID'] == DBID:
                return True
        return False
    #添加申请
    def AddApplyList(self, DBID, IsYao = False):
        if self.IsExistPlayer(DBID):
            return
        ApplyInfo = {'DBID':DBID, 'IsYao':IsYao }
        self.ApplyList.append(ApplyInfo)
        self.client.onYaoShuStatus(self.ApplyList,self.AcceptList,self.YaoEndTime)
        DEBUG_MSG("AddApplyList:%s" % str(self.ApplyList) )
        
    def ChangeApplyList(self, DBID, IsYao):
        for ApplyInfo in self.ApplyList:
            if ApplyInfo['DBID'] == DBID :
                ApplyInfo['IsYao'] = IsYao
                if hasattr(self,'client') and self.client:
                    self.client.onYaoShuStatus(self.ApplyList,self.AcceptList,self.YaoEndTime)
                DEBUG_MSG("ChangeApplyList:%s" % (str(ApplyInfo)) )
    #接受请求
    def AddAcceptList(self, DBID, YaoEndTime ):
        AcceptInfo = {'DBID':DBID, 'YaoEndTime':YaoEndTime }
        self.AcceptList.append(AcceptInfo)
        self.client.onYaoShuStatus(self.ApplyList,self.AcceptList,self.YaoEndTime)
        DEBUG_MSG("AddAcceptList:%d" % DBID )

    def SetYaoEndTime(self):
        if self.YaoEndTime == 0:
            YaoShu = self.GetConfigYaoShu(1001)
            if YaoShu is not None:
                self.YaoEndTime = int(time.time() ) + YaoShu['CD']*60
                self.client.onYaoShuStatus(self.ApplyList,self.AcceptList,self.YaoEndTime)
        DEBUG_MSG("SetYaoEndTime:%i" % (self.YaoEndTime ) )

    def CheckYaoEndTime(self, nowtime):
        if self.YaoEndTime != 0 and nowtime > self.YaoEndTime:
            self.MasterYaoShuHandler()

    #场主摇树处理
    def MasterYaoShuHandler(self, YaoEndTime = None):
        IsSuccess = True
        if YaoEndTime:
            self.YaoEndTime = YaoEndTime
        #收获自己
        playerNum = self.GetYaoShuPlayerNum()
        ItemIDList = self.Component("Land").GetItemListByStage('摇树')
        INFO_MSG("MasterYaoShuHandler:%s,%i" % ( str(ItemIDList), playerNum) )
        #摇树大于两个人
        if playerNum >= 2:
            IdList = ItemIDList[:]
            #自己收获
            for ItemType in IdList:
                if not self.MasterGet(ItemType,playerNum):
                    ItemIDList.remove(ItemType)
            #别人收获
            for ApplyInfo in self.ApplyList:
                if ApplyInfo['IsYao']:
                    KBEngine.createEntityFromDBID("Account", ApplyInfo['DBID'],
                    Functor.Functor(self.CallBackOtherYaoShu, self.YaoEndTime,self.owner.Data['name'],playerNum,ItemIDList ) )
        else:
            self.SYSMessage(0, 3014, self.YaoEndTime )
            IsSuccess = False
        #清空厂主的数据
        self.ClearMaster()
        return IsSuccess
        
    def ClearMaster(self):
        #清空列表
        self.ApplyList = []
        self.YaoEndTime = 0
        if hasattr(self,'client') and self.client:
            self.client.onYaoShuStatus(self.ApplyList,self.AcceptList,self.YaoEndTime)
        DEBUG_MSG("ClearMaster:%s,%s,%i" % ( self.ApplyList,self.AcceptList, self.YaoEndTime ) )

    def ClearOter(self, MasterDBID):
        for index,AcceptInfo in enumerate(self.AcceptList):
            if AcceptInfo['DBID'] == MasterDBID:
                del self.AcceptList[index]
                DEBUG_MSG("ClearOter:%s" % ( self.AcceptList ) )

    #其他人摇树收益
    def CallBackOtherYaoShu(self,YaoEndTime,MasterName,playerNum,ItemIDList,baseRef,databaseID,wasActive):
        INFO_MSG("CallBackOtherYaoShu:%i,%i" % (databaseID, wasActive) )
        if baseRef is None:
            DEBUG_MSG("CallBackOtherYaoShu baseRef error:%i" % databaseID)
            # if self.owner is not None:
            #     self.GetGenerator('CallBackOtherYaoShu').Set(databaseID,self.CallBackOtherYaoShu,YaoEndTime,MasterName,playerNum,ItemIDList)
        else:
            #获得收益
            Friends = baseRef.getComponent("Friends")
            if playerNum >= 2:            #self.GetMinPlayNum(1001)    
                for ItemType in ItemIDList:
                    yaoHarvest = self.GetHarvestbyNum(ItemType, playerNum)
                    if yaoHarvest == 0:
                        continue
                    Friends.OtherGet(ItemType, yaoHarvest,YaoEndTime,MasterName)
            DEBUG_MSG("OtherYaoShu:%i,%s,%i,%s" % ( YaoEndTime,MasterName,playerNum,str(ItemIDList) ) )
            if not wasActive:
                baseRef.destroy()

    #场主的收益
    def MasterGet(self, ItemType,playerNum):
        #根据当前摇树人数获得对应的收益
        yaoHarvest = self.GetHarvestbyNum(ItemType, playerNum)
        #结算自己的摇树
        #自己的剩余收益 -= 摇树人数 * d_Harvest
        surpHarvest = self.Component("Land").GetAllLandHarvest(ItemType, 'surpHarvest')
        surpHarvest -= playerNum * yaoHarvest
        if surpHarvest <= 0:
            INFO_MSG("surpHarvest:%i,%i,%i" % ( yaoHarvest,surpHarvest,playerNum ) )
            return False
        #获得对应产品
        d_Item = self.Component("Land").GetOutItem(ItemType)
        self.Component("bags").AddItem(d_Item['ID'], surpHarvest, '摇树收益')
        #记录消息日志
        self.SYSMessage(0, 3011, self.YaoEndTime , surpHarvest, d_Item['ItemName'])
        #改变枯树期时间
        deltime = self.GetdeltimebyNum(ItemType, playerNum)
        self.Component("Land").OnYaoshuEndHandler(ItemType, self.YaoEndTime, deltime)
        return True

    #结算其他人的收益
    def OtherGet(self, ItemType, yaoHarvest,YaoEndTime,MasterName):
        #结算别人的摇树
        #根据当前摇树人数获得对应的收益
        d_Item = self.Component("Land").GetOutItem(ItemType)
        self.Component("bags").AddItem(d_Item['ID'], yaoHarvest,'帮好友摇树收益')
        self.SYSMessage(0, 3007, YaoEndTime , MasterName, yaoHarvest,'E币')
        DEBUG_MSG("OtherGet:%i,%i,%i" % ( ItemType,d_Item['ID'], yaoHarvest ) )
    '''
	 邀请 好友摇树
	'''
    def reqApplyYaoShu(self, DBID):
        DEBUG_MSG("reqApplyYaoShu:%i" % (DBID) )
        #是否有摇树土地
        if not self.Component("Land").IsYaoShuLand():
            return -1
        #是否有管家
        if self.Component("Land").IsHaveGJ():
            self.client.onApplyYaoShu('有管家不能申请摇树')
            return -2 
        #设置摇树结束时间
        self.SetYaoEndTime()
        #是否超出摇树时间
        nowTime = int(time.time())
        if nowTime > self.YaoEndTime:
            self.client.onApplyYaoShu('超出摇树时间')
            return -3
        self.AddApplyList(DBID)
        #给在线离线好友发送系统消息
        self.SYSMessage(DBID,3005, nowTime, self.owner.databaseID,self.owner.Data['name'], self.YaoEndTime,0)
        self.client.onApplyYaoShu('成功')
        return 0
    
    '''
	 接受 好友摇树
	'''
    #摇好友摇树，在收到好友请求后 DBID：邀请自己摇树的人
    def reqAcceptYaoShu(self, DBID, MesaageUUID, IsAccept):
        DEBUG_MSG("reqAcceptYaoShu:%i,%i,%i" % (DBID, MesaageUUID, IsAccept) )
        if IsAccept == 2:
            self.SYSMessage(DBID, 3015, int(time.time()), self.owner.Data['name'])
        self.ChangeMessageState(MesaageUUID, IsAccept)
        self.client.onAcceptYaoShu('成功')
    '''
	 摇树
	'''
	#摇树，需要客户端传递对应的消息，来更新消息状态
    def reqYaoShu(self, DBID, MesaageUUID ):
        DEBUG_MSG("reqYaoShu:%i" % (DBID) )
        self.BuildGenerator('CallbackYaoShu')
        KBEngine.createEntityFromDBID("Account", DBID, Functor.Functor(self.CallbackYaoShu))
        self.ChangeMessageState(MesaageUUID, 3)

    def CallbackYaoShu(self, baseRef, databaseID, wasActive):
        if baseRef is None:
            DEBUG_MSG("CallbackYaoShu baseRef error:%i" % databaseID)
            if self.owner is not None:
                self.GetGenerator('CallbackYaoShu').Set(databaseID,self.CallbackYaoShu)
        else:
            Friends = baseRef.getComponent("Friends")
            Land = baseRef.getComponent("Land")
            #判断是否超出摇树时间
            if int(time.time()) > Friends.YaoEndTime:
                self.client.onYaoShu('已经不能摇树了')
            # elif Land.IsHaveGJ():
            #     self.client.onYaoShu('已经不能摇树了')    
            elif Friends.GetYaoShuPlayerNum() >= 10:
                self.client.onYaoShu('已经不能摇树了')
            else:
                #添加到自己的接受列表		
                self.AddAcceptList(databaseID, Friends.YaoEndTime)
                #设置摇树
                Friends.ChangeApplyList(self.owner.databaseID, True)
                self.client.onYaoShu('成功')
            if not wasActive:
                baseRef.destroy()

    '''
	 获得摇树状态，申请列表，接受列表
	'''
    def reqYaoShuStatus(self):
        if hasattr(self,'client') and self.client:
            self.client.onYaoShuStatus(self.ApplyList,self.AcceptList,self.YaoEndTime)
        DEBUG_MSG("reqYaoShuStatus:%i, %s, %s" % (self.owner.databaseID, str(self.ApplyList),str(self.AcceptList) ) )

    #根据摇树人数 获得每人的收益
    def GetHarvestbyNum(self, ItemType, playerNum):
        d_YaoShu = self.GetConfigYaoShu(ItemType)
        if d_YaoShu is None:
            return 0
        if d_YaoShu['Harvest']:
            for i, num in enumerate(d_YaoShu['num']):
                if num == playerNum:
                    return d_YaoShu['Harvest'][i]
            return d_YaoShu['Harvest'][-1]
        else:
            return 0

    #根据偷树人数 获得 减少的枯树时间
    def GetdeltimebyNum(self, ItemType, playerNum):
        d_YaoShu = self.GetConfigYaoShu(ItemType)
        if d_YaoShu is None:
            return -1
        if d_YaoShu['deltime']:
            for i, num in enumerate(d_YaoShu['num']):
                if num == playerNum:
                    return d_YaoShu['deltime'][i]
            return d_YaoShu['deltime'][-1]
        else:
            return 0

    def GetMinPlayNum(self, ItemType):
        d_YaoShu = self.GetConfigYaoShu(ItemType)
        if d_YaoShu is None:
            return -1
        return d_YaoShu['num'][0]

    '''
	 邀请 好友偷树
	'''
    def reqApplySteal(self, FriendDBID, StealDBID , StealName): 
        DEBUG_MSG("reqApplySteal:%i,%i" % (FriendDBID,StealDBID) )
        #通知好友偷树
        self.SYSMessage(FriendDBID, 3006, int(time.time()), self.owner.databaseID,self.owner.Data['name'],StealName, StealDBID,0)

    def reqAcceptSteal(self, DBID, MesaageUUID, IsAccept):   
        if IsAccept == 2:
            self.SYSMessage(DBID, 3016, int(time.time()), self.owner.Data['name'])
        self.ChangeMessageState(MesaageUUID, IsAccept)
    
    '''
	 陌生人检测是否可偷
	'''
    #好友家使用
    #DBIDList:偷者的DBID的列表, ByDBID: 被偷者的DBID
    # def reqCheckCanSteal(self, DBIDList , ByDBID):
    #     self.BuildGenerator('CallBackCheckSteal')
    #     KBEngine.createEntityFromDBID("Account", ByDBID, Functor.Functor(self.CallBackCheckSteal,DBIDList))

    # def CallBackCheckSteal(self, DBIDList, baseRef, databaseID, wasActive):
    #     if baseRef is None:
    #         DEBUG_MSG("CallBackCheckSteal baseRef error:%i" % databaseID)
    #         if self.owner is not None:
    #             self.GetGenerator('CallBackCheckSteal').Set(databaseID,self.CallBackCheckSteal,DBIDList)
    #     else:
    #         Land = baseRef.getComponent("Land")
    #         CanStealList = []
    #         for DBID in DBIDList:
    #             IsCan, LandList = Land.IsAllCanSteal(DBID)
    #             CanStealList.append({'DBID':DBID,'CanSteal':IsCan})
    #         self.client.onCheckCanSteal(CanStealList, databaseID)
    #         DEBUG_MSG("CallBackCheckSteal:%s,%i" % (str(CanStealList),databaseID) )
    #         if not wasActive:
    #             baseRef.destroy()

    # #消息框使用
    # #DBID:偷者的DBID, ByDBID: 被偷者的DBID
    # def reqCheckMessageCanSteal(self, DBID , ByDBID, MesaageUUID):
    #     self.BuildGenerator('CallBackCheckMessageCanSteal')
    #     KBEngine.createEntityFromDBID("Account", ByDBID, Functor.Functor(self.CallBackCheckMessageCanSteal,DBID,MesaageUUID))

    # def CallBackCheckMessageCanSteal(self, DBID,MesaageUUID, baseRef, databaseID, wasActive):
    #     if baseRef is None:
    #         DEBUG_MSG("CallBackCheckMessageCanSteal baseRef error:%i" % databaseID)
    #         if self.owner is not None:
    #             self.GetGenerator('CallBackCheckMessageCanSteal').Set(databaseID,self.CallBackCheckMessageCanSteal,DBID,MesaageUUID)
    #     else:
    #         Land = baseRef.getComponent("Land")
    #         IsCan, LandList = Land.IsAllCanSteal(DBID)   
    #         self.client.onCheckMessageCanSteal(IsCan, MesaageUUID)
    #         DEBUG_MSG("CallBackCheckMessageCanSteal:%i,%i" % (IsCan,MesaageUUID) )
    #         if not wasActive:
    #             baseRef.destroy()
    
    # def CheckFriendCanSteal(self):
    #     CurCount = 0
    #     INFO_MSG("CheckFriendCanSteal:%i" % len(self.FriendList))
    #     for friendInfo in self.FriendList:
    #         CurCount += 1
    #         KBEngine.createEntityFromDBID("Account", friendInfo['DBID'], 
    #         Functor.Functor(self.CallBackCheckFriendCanSteal,self.owner.databaseID,CurCount,len(self.FriendList)) )

    # def CallBackCheckFriendCanSteal(self, DBID,CurCount,MaxCount, baseRef, databaseID, wasActive):
    #     if baseRef is None:
    #         DEBUG_MSG("CallBackCheckFriendCanSteal baseRef error:%i" % databaseID)
    #     else:
    #         Land = baseRef.getComponent("Land")
    #         IsCan, LandList = Land.IsAllCanSteal(DBID)   
    #         self.ChangeFriendInfo(databaseID,'CanSteal', int(IsCan) )
    #         if CurCount >= MaxCount: 
    #             self.reqFriendList()
    #             DEBUG_MSG("CallBackCheckFriendCanSteal %d,%d" %(CurCount, MaxCount) )
    #         if not wasActive:
    #             baseRef.destroy()
    '''
	 陌生人检测是否可偷
	'''
    #批量检测好友是否可偷
    #DBIDList:偷者的DBID的列表, ByDBID: 被偷者的DBID
    def reqCheckCanSteal(self, DBIDList , ByDBID):
        self.IsCanStealList = []
        self.StealCount = 0 
        self.StealMaxCount = len(DBIDList)
        for stealDBID in DBIDList:
            self.CheckCanSteal(stealDBID,ByDBID, self.CheckCanStealCallback )

    def CheckCanStealCallback(self, stealDBID, ByStealDBID, IsCanSteal):
        self.IsCanStealList.append({'DBID':stealDBID,'CanSteal':IsCanSteal})
        self.StealCount +=1
        if self.StealCount >= self.StealMaxCount: 
            self.client.onCheckCanSteal(self.IsCanStealList, ByStealDBID)
            self.StealCount = 0
            DEBUG_MSG("CheckCanStealCallback:%s,%i" % (str(self.IsCanStealList),ByStealDBID) )
        DEBUG_MSG("Steal StealCount:%i,%i" % (self.StealCount,self.StealMaxCount) )

    #消息框里检测是否可偷
    #DBID:偷者的DBID, ByDBID: 被偷者的DBID
    def reqCheckMessageCanSteal(self, DBID , ByDBID, MesaageUUID):
        self.CheckCanSteal(DBID,ByDBID,Functor.Functor(self.CheckMessageCanStealCallback, MesaageUUID) )
       
    def CheckMessageCanStealCallback(self, MesaageUUID, stealDBID, ByStealDBID, IsCanSteal):
        self.client.onCheckMessageCanSteal(IsCanSteal, MesaageUUID)
        DEBUG_MSG("CheckMessageCanStealCallback:%i,%i" % (IsCanSteal,MesaageUUID) )

    #检测好友是否可偷
    def CheckFriendCanSteal(self):
        INFO_MSG("CheckFriendCanSteal:%i" % len(self.FriendList))
        owerDBID = self.owner.databaseID
        for friendInfo in self.FriendList:
            self.CheckCanSteal(owerDBID, friendInfo['DBID'],self.CheckFriendCanStealCAllback)

    def CheckFriendCanStealCAllback(self, stealDBID, ByStealDBID, IsCanSteal):
        self.ChangeFriendInfo(ByStealDBID,'CanSteal', IsCanSteal )

    #stealDBID: 偷者  ByStealDBID： 被偷者
    def CheckCanSteal(self,stealDBID, ByStealDBID,callback):
        sql = "select count(*) from kbe.tbl_Account_Land_LandData where parentID in (select id from kbe.tbl_Account_Land where parentID = %i) \
        and sm_stage = 6 and sm_surpHarvest > (sm_Harvest/2) and not find_in_set('%i',sm_StealList) " % (ByStealDBID,stealDBID)
        KBEngine.executeRawDatabaseCommand(sql, Functor.Functor(self.CanStealsqlcallback, stealDBID, ByStealDBID,callback))
        #DEBUG_MSG("can steal sql :%s" % (sql) )

    def CanStealsqlcallback(self,stealDBID,ByStealDBID,callback, result, rows, insertid, error):
        if len(result) > 0:
            print("result====================")
            print(result)
            count = bytes.decode(result[0][0])
            if int(count) > 0: 
                callback(stealDBID,ByStealDBID,1)  #可以偷
                DEBUG_MSG("CanStealsqlcallback steal:%i,bySteal:%i,count:%i " % (stealDBID,ByStealDBID,int(count) ) )
            else:
                callback(stealDBID,ByStealDBID,0)        
        else:
            callback(stealDBID,ByStealDBID,0)
      
    '''
	 偷树
	'''
    #被消息邀请偷树，需要填消息的MesaageUUID
    def reqSteal(self, DBID, Name, MesaageUUID):
        INFO_MSG("reqSteal:%i,%s" % (DBID, Name) )
        self.BuildGenerator('CallBackSteal')	
        KBEngine.createEntityFromDBID("Account", DBID, Functor.Functor(self.CallBackSteal,Name))
        self.ChangeMessageState(MesaageUUID,3)
			
    def CallBackSteal(self, Name, baseRef, databaseID, wasActive):
        INFO_MSG("CallBackSteal:%i,%i" % (databaseID, wasActive) )
        if baseRef is None:
            DEBUG_MSG("CallBackSteal baseRef error:%i" % databaseID)
            if self.owner is not None:
                self.GetGenerator('CallBackSteal').Set(databaseID,self.CallBackSteal,Name)
        else:
            #传入当前用户的ID
            Land = baseRef.getComponent("Land")
            owerDBID = self.owner.databaseID   #owerDBID：偷树人DBID， databaseID：被偷者DBID
            owerName = self.owner.Data['name']  #owerName:偷树人名字, Name:被偷者名字
            res,StealTotalInfo,StealLandInfo = Land.BySteal(owerDBID)
            #获得偷到东西
            if res == -1:
                self.client.onSteal('该土地不可偷', [{'LandID':0,'StealValue':0}])
            elif res == -2:
                self.SYSMessage(databaseID, 3002, int(time.time()) , owerName)
                self.SYSMessage(0, 3010, int(time.time()) , Name)
                self.SYSMessage(databaseID, 5002, int(time.time()) , owerName)
                self.client.onSteal('被管家抓住，毫无收获', [{'LandID':0,'StealValue':0}])
            else:
                for outItemType, stealValue in StealTotalInfo.items():
                    if stealValue != 0:
                        self.Component("bags").AddItem(outItemType, stealValue,'偷树收益')
                        #通知自己偷树成功
                        if res == 0:
                            self.SYSMessage(databaseID, 3001, int(time.time()) , owerName, stealValue,'E币')
                            self.SYSMessage(0, 3008, int(time.time()) , Name, stealValue,'E币')
                            self.client.onSteal('恭喜偷树成功，偷走了%.2f个E币' % (stealValue/100), StealLandInfo)
                        else:
                            self.SYSMessage(databaseID, 3003, int(time.time()) , owerName, stealValue,'E币')
                            self.SYSMessage(0, 3009, int(time.time()) , Name, stealValue,'E币')
                            self.SYSMessage(databaseID, 5002, int(time.time()) , owerName)
                            self.client.onSteal('被管家抓住，只偷走了%.2f个E币' % (stealValue/100), StealLandInfo)
            if not wasActive:
                baseRef.destroy()




 