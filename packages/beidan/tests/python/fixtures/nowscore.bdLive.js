var isIE10 = false;
try{
if((document.all && document.documentMode == 10) != undefined) isIE10 = (document.all && document.documentMode == 10);
}catch(e){}
//定义Config
var Config = new Object();
Config.rank= 0;
Config.redcard = 1;
Config.goalNotify = 1;


//北京单场比分直播相关脚本
if (!window.createPopup) {
    var __createPopup = function() {
        var SetElementStyles = function(element, styleDict) {
            var style = element.style;
            for (var styleName in styleDict) style[styleName] = styleDict[styleName];
        }
        var eDiv = document.createElement('div');
        SetElementStyles(eDiv, { 'position': 'absolute', 'top': 0 + 'px', 'left': 0 + 'px', 'width': 0 + 'px', 'height': 0 + 'px', 'zIndex': 1000, 'display': 'none', 'overflow': 'hidden' });
        eDiv.body = eDiv;
        var opened = false;
        var setOpened = function(b) {
            opened = b;
        }
        var getOpened = function() {
            return opened;
        }
        var getCoordinates = function(oElement) {
            var coordinates = { x: 0, y: 0 };
            while (oElement) {
                coordinates.x += oElement.offsetLeft;
                coordinates.y += oElement.offsetTop;
                oElement = oElement.offsetParent;
            }
            return coordinates;
        }
        return { htmlTxt: '',
            document: eDiv,
            isOpen: getOpened(),
            isShow: false,
            hide: function() {
                SetElementStyles(eDiv, { 'top': 0 + 'px', 'left': 0 + 'px', 'width': 0 + 'px', 'height': 0 + 'px', 'display': 'none' });
                eDiv.innerHTML = '';
                this.isShow = false;
            },
            show: function(iY, iX, iWidth, iHeight, oElement) {
                if (!getOpened()) {
                    document.body.appendChild(eDiv); setOpened(true);
                };
                this.htmlTxt = eDiv.innerHTML;
                if (this.isShow) { this.hide(); };
                eDiv.innerHTML = this.htmlTxt;
                var coordinates = getCoordinates(oElement);
                eDiv.style.top = (iX + coordinates.x) + 'px';
                eDiv.style.left = (iY + coordinates.y) + 'px';
                eDiv.style.width = iWidth + 'px';
                eDiv.style.height = iHeight + 'px';
                eDiv.style.display = 'block';
                this.isShow = true;
            }
        }
    }
    window.createPopup = function() {
        return __createPopup();
    }
}

//显示进球窗口
var startani_C,startani_A,startani_B,pop_TC;
var oPopup;
try{ oPopup=window.createPopup();}
catch(e){}

function ShowCHWindow(str,matchnum)
{
imagewidth=480;
imageheight=24+34*matchnum ;
var st;

st="<table width=480 border=0 cellpadding=1 cellspacing=0 bgcolor=#E0B22B style='font-size: 13px;'>";
st=st + "  <tr><td><table width=478 border=0 cellpadding=0 cellspacing=0>";
st=st + "	  <tr><td colspan=6 style='line-height:22px;font-weight:bold;color:#880000;font-size:14px;background-image:url(/images/soccerbg.png);background-repeat: repeat-x;background-position: left top;text-align:center;'>捷报比分 入球提示</td></tr>";
st=st + str;
st=st + "	</table></td>";
st=st + "  </tr>";
st=st + "</table>";  
st=st + "<style type='text/css'>";
st=st + ".line td { border-bottom:solid 1px #FFD8CA; line-height:32px;}";
st=st + "</style>";

y=1;
x=(screen.width-imagewidth)/2;

oPopupBody = oPopup.document.body;
oPopupBody.innerHTML = st;
oPopupBody.style.cursor="pointer";
oPopupBody.title = "点击关闭";
oPopupBody.onclick=dismisspopup;
oPopupBody.oncontextmenu=dismisspopup;
pop_TC=40;
pop();
}
function pop(){
  try{
	oPopup.show(x,y,imagewidth, imageheight);
	startani_A=setTimeout("pop()",300);  //显示15秒
	if(pop_TC<0){dismisspopup();};
	pop_TC=pop_TC-1;
  }catch(e){}
}
function dismisspopup()
{	clearTimeout(startani_A);
	oPopup.hide();
}

var zXml = {
	useActiveX: (typeof ActiveXObject != "undefined"),
	useXmlHttp: (typeof XMLHttpRequest != "undefined")
};

zXml.ARR_XMLHTTP_VERS = ["MSXML2.XmlHttp.6.0","MSXML2.XmlHttp.3.0"];

function zXmlHttp() {}

zXmlHttp.createRequest = function ()
{
	if (zXml.useXmlHttp)  return new XMLHttpRequest(); 

	if(zXml.useActiveX)  //IE < 7.0 = use ActiveX
	{  
		if (!zXml.XMLHTTP_VER) {
			for (var i=0; i < zXml.ARR_XMLHTTP_VERS.length; i++) {
				try {
					new ActiveXObject(zXml.ARR_XMLHTTP_VERS[i]);
					zXml.XMLHTTP_VER = zXml.ARR_XMLHTTP_VERS[i];
					break;
				} catch (oError) {}
			}
		}		
		if (zXml.XMLHTTP_VER) return new ActiveXObject(zXml.XMLHTTP_VER);
	} 
	alert("对不起，您的电脑不支持 XML 插件，请安装好或升级浏览器。");
};


//Return result type string 
function MatchState(state){
	switch(parseInt(state)){
		case 0:
			return "<font color=#3366ff>未开赛</font>";
		case 1:
			return "<font color=blue>上</font>";
		case 2:
			return "<font color=blue>中场</font>";
		case 3:
			return "<font color=blue>下</font>";
		case 4:
			return "<font color=red>完场</font>";
	    case 5:
	        return "<font color=blue>点球</font>";
	    case -10:
			return "取消";
		case -11:
			return "待定";
		case -12:
			return "腰斩";
		case -13:
			return "中断";
		case -14:
			return "推迟";
		case -1:
			return "<font color=red>完场</font>";
		case -10:
		case -99:
			return "取消";
	}
	return "";
}



function GetCompanyByID(ID){
	switch(parseInt(ID)){
		case 1: return "澳M";
		case 2: return "波*";
		case 3: return "皇G";
		case 4: return "立B";
		case 8: return "36*";   
		case 9: return "WL"; 
		case 12: return "易S";
		case 14: return "韦D";
		case 17: return "明S";
		case 18: return "Euro*";
		case 19: return "Inter*";
		case 22: return "10*";
		case 23: return "金宝*";
		case 24: return "12*";
		case 28: return "明S"; 
		case 29: return "乐天*";   
		case 30: return "沙*"; 
		case 31: return "利*";
		case 33: return "永利*";
		case 35: return "盈*";
	}
}


//加载页面时显示红牌
function ShowRedCard(value){
	if(value!=null)
		writeCookie("RedCard",value);
	else{
		value=eval(getCookie("goalNotify"));//初始化进球提示
		if(value==null) value=true; //默认显示
		if(!value) getByID("chkSoundTips").checked=false;
		if(!value) Config.goalNotify = 0;	

		value=eval(getCookie("RedCard"));
		if(value==null) value=true; //默认显示
		if(!value) return;
		if(value)  getByID("chkCardRed").checked=true;
	}
	if(value) Config.redcard = 1;
	else Config.redcard = 0;	
   for(var i=1;i<=MatchCount;i++){ //赛程表
	  try{
		if(M[i][9]>0){
			if(value)
				getByID("HomeRed_" + M[i][0]).innerHTML="<img src='/images/redcard" + M[i][9] +".gif'>";
			else
				getByID("HomeRed_" + M[i][0]).innerHTML="";
		}		
		if(M[i][10]>0){
			if(value)
				getByID("GuestRed_" + M[i][0]).innerHTML="<img src='/images/redcard" + M[i][10] +".gif'>";
			else
				getByID("GuestRed_" + M[i][0]).innerHTML="";
		}
	  }catch(e){}
   } 
}

function CheckGoalNotify(value){
    writeCookie('goalNotify',value)
    if(value)
        Config.goalNotify=1;
    else
        Config.goalNotify=0;
}

//是否显示已经停售的赛程
function ShowOverSale(value) {
	if(value!=null)
		writeCookie("ShowOver",value);
	else{
		value=eval(getCookie("ShowOver")); 
		if(value==null) value=true; //默认显示
		if(value) return;
		getByID("chkUnSale").checked=false;
	}
	var num=parseInt(getByID("hide_num").innerHTML);
	var tr=getByID("MatchTable").getElementsByTagName("tr");
	var saleState;
	for(var i=0;i<tr.length;i++){
		saleState=tr[i].getAttribute("cansale")
		if(saleState==null) continue;
		if(saleState=="false"){
			if(value && tr[i].style.display!=""){
				tr[i].style.display="";
				num--;
			}
			if(!value && tr[i].style.display!="none"){
				tr[i].style.display="none";
				num++;
			}
		}
	}
	getByID("hide_num").innerHTML=num;
}

// 隐藏某场比赛 
function hideRow(rowId) {
	getByID(rowId).style.display = "none";
	var id = parseInt(rowId.split('_')[1]);
	if (M[id][25] != undefined && M[id][25] != "" && getByID("Explain_" + M[id][0])!=undefined) getByID("Explain_" + M[id][0]).style.display = "none";
	getByID("hide_num").innerHTML = parseInt(getByID("hide_num").innerHTML) + 1;
}

// 将已隐藏的场次显示出来
function showHided() {
	for(i=1;i<=MatchCount;i++)
	{
	   	var row=getByID("row_"+i); 
	   	if(row) row.style.display="";	
	   	if (M[i][25] != undefined && M[i][25] != "" && getByID("Explain_" + M[i][0])!=undefined) getByID("Explain_" + M[i][0]).style.display = "";
       }
	var gameName=document.getElementsByName("gameName");
	for(i=0;i<gameName.length;i++)
	{
	   	gameName[i].checked=true;
	}
	var ballType=document.getElementsByName("ballType");
	if(ballType)
	{
	    for(i=0;i<ballType.length;i++)
	    {
	   	    ballType[i].checked=true;
	    }
	}
	//停售赛事开关
	if (getByID("chkUnSale")) getByID("chkUnSale").checked = true;
	// 重置让球与不让球设置
	var tempObj = getByID("chkHandicap");
	if (tempObj) tempObj.checked = true;
	tempObj = getByID("chkUnHandicap");
	if (tempObj) tempObj.checked = true;

	getByID("hide_num").innerHTML="0";
	
	if(getByID("onlyChooseShowID")) getByID("onlyChooseShowID").checked = false;
}

//选择某个联赛
function SelectSclass(checked,sclass){
	var num=parseInt(getByID("hide_num").innerHTML);
	var display;
	for(i=1;i<=MatchCount;i++)
	{
	   	var row=getByID("row_"+i); 
	   	if(row && row.getAttribute("gamename")==sclass){
	   		display= checked?"":"none";
	   		if(row.style.display!=display){
	   			row.style.display=display;
	   			if(checked) num--;
	   			else num++
	   			if (M[i][25] != undefined && M[i][25] != "" && getByID("Explain_" + M[i][0])!=undefined) getByID("Explain_" + M[i][0]).style.display = display;
           }
	   	}
	}
	getByID("hide_num").innerHTML=num;
}
//联赛反选
function ReverseSclass(){
	var num=0;
	var display;
	var gameName=document.getElementsByName("gameName"); 
	for(var i=0;i<gameName.length;i++){
		gameName[i].checked=!gameName[i].checked;
		var sclass=gameName[i].value;
		for(var j=1;j<=MatchCount;j++)
		{
	   		var row=getByID("row_"+j); 
	   		if(row && row.getAttribute("gamename")==sclass){
	   			display= gameName[i].checked?"":"none";
	   			if(row.style.display!=display){
	   				row.style.display=display;
	   				if(!gameName[i].checked) num++
	   				if (M[j][25] != undefined && M[j][25] != "" && getByID("Explain_" + M[j][0])!=undefined) getByID("Explain_" + M[j][0]).style.display = display;
	   			}
	   		}
		}
	}
	getByID("hide_num").innerHTML=num;
}


// 切换让球和不让球场次,参数:true 让球,false 非让球;  选中开关
function ShowHandicapMatch(handicap,checked){
	var num=parseInt(getByID("hide_num").innerHTML);
	var display;
	for(i=1;i<=MatchCount;i++)
	{
	   	var row=getByID("row_"+i); 
	   	if(row==null) continue;
	   	if(handicap && row.getAttribute("polygoal")!="0" || !handicap && row.getAttribute("polygoal")=="0"){
	   		display= checked?"":"none";
	   		if(row.style.display!=display){
	   			row.style.display=display;
	   			if(checked) num--;
	   			else num++
	   		}
	   	}
	}
	getByID("hide_num").innerHTML=num;
}

//加载页面时显示比赛备注
function ShowAllExplain() {
    for (var i = 1; i <= MatchCount; i++) { //赛程表
        try {
            if (M[i][25] != undefined && M[i][25] != "" && getByID("Explain_" + M[i][0])!=undefined) {
                getByID("Explain_" + M[i][0]).innerHTML="<td colspan=13 style='padding-right:100px;'>" + showExplain(M[i][25], M[i][17], M[i][20], M[i][23]) + "</td><td style='display:none'></td><td></td>";
                getByID("Explain_" + M[i][0]).style.display="";
            }
        } catch (e) { }
    }
}

//更新比赛进行的时间,判断是否截止
function UpdateMatchTimer(){
	//各彩种的投注选项个数
	var OptionNum=3;
	if(TypeID==5) OptionNum=3;
	if(TypeID==6) OptionNum=8;
	if(TypeID==7) OptionNum=4;
	if(TypeID==8) OptionNum=25;
	if(TypeID==9) OptionNum=9;	
	
	for(var i=1;i<=MatchCount;i++){
	  try{
		if(M[i][13]==1){  //未开场		
			if(new Date()-difftime>M[i][3]){//截止  使选择功能无效
				M[i][13]=0;
				getByID("row_"+i).cansale="false";
				for(var j=1;j<=OptionNum;j++){
				    var td=getByID("cell_"+ i +"_"+ j);
					td.removeAttribute("onClick");
					td.removeAttribute("style");
					td.removeAttribute("bgcolor");
					if(getByID("checkbox_"+i+"_"+ j)) getByID("checkbox_"+i+"_"+ j).disabled=true;
				}
				if(getByID("selall"+i)) getByID("selall"+i).disabled=true;

				getByID("unSaleNum").innerHTML=parseInt(getByID("unSaleNum").innerHTML)+1;
				if(getByID("chkUnSale").checked==false && getByID("row_"+i).style.display==""){
					getByID("row_"+i).style.display="none";
					getByID("hide_num").innerHTML=parseInt(getByID("hide_num").innerHTML)+1;
				}
				getByID("row_"+i).cells[3].innerHTML="截止";
			}
		}
		if(M[i][4]==1){  //上半场			
			goTime = Math.floor((new Date()-M[i][2]-difftime)/60000);
			if(goTime>45) goTime = "45+";
			if(goTime<1)  goTime = "1";
			document.getElementById("row_" +  i).cells[3].innerHTML = "<font color=blue>" + goTime +  "</font><img src='/images/in.gif' border=0>";
		}
		if(M[i][4]==3){  //下半场		
			goTime = Math.floor((new Date()-M[i][2]-difftime)/60000)+46;
			if(goTime>90) goTime = "90+";
			if(goTime<46) goTime = "46";
			document.getElementById("row_" +  i).cells[3].innerHTML = "<font color=blue>" + goTime +  "</font><img src='/images/in.gif' border=0>";
		}
	  }catch(e){}
	}
	runtimeTimer=window.setTimeout("UpdateMatchTimer()",30000);
}



var oXmlHttp = zXmlHttp.createRequest();
var lastXmlContent="";
var hasHandicapCol=0;
if(TypeID==5 && typeof(SaleCount)!="undefined") hasHandicapCol=1; //胜负平玩法多一列让球

function getxml()
{
	oXmlHttp.open("get","/info/match/data/change.xml?" + Date.parse(new Date()),true);
	oXmlHttp.onreadystatechange = refresh;			
	oXmlHttp.send(null);
	window.setTimeout("getxml()",4000);
}

function refresh()
{
	if(oXmlHttp.readyState!=4 || (oXmlHttp.status!=200 && oXmlHttp.status!=0)) return;
	if(oXmlHttp.responseText=="" || oXmlHttp.responseText==lastXmlContent) return;
	lastXmlContent=oXmlHttp.responseText;

	var root=oXmlHttp.responseXML.documentElement;

	var D=new Array();
	var score1change, score2change, scorechange;
	var goTime,hometeam,guestteam,sclassname,score1,score2,tr;	
	var matchNum=0,id;
	var winStr="";
		
	for(var i = 0;i<root.childNodes.length;i++)
	{	 
	   if(document.all && !isIE10)
			D=root.childNodes[i].text.split("^"); //0:ID,1:state,2:score1,3:score2,4:half1,5:half2,6:card1,7:card2,8:time1,9:time2,10:explain,11:lineup		
	   else
			D=root.childNodes[i].textContent.split("^");
		D[1]=parseInt(D[1]);
		if(D[1]==4) D[1]=-1; //加时转完场
		id=0;
		for(var j=1;j<=MatchCount;j++){
			if(M[j][0]==D[0]){
				id=j
				break;
			}
		}
		if(id==0) continue;// 非北单比赛
		if(D[1]==0) continue;//未开场
		tr=document.getElementById("row_" + id);
		if(tr==null)  continue;  
		if(M[id][23]==true) //主客调转
		{
			var a=D[2];
			D[2]=D[3];
			D[3]=a;
			
			a=D[4];
			D[4]=D[5];
			D[5]=a;

			a=D[6];
			D[6]=D[7];
			D[7]=a;		
		}
		score1change=false;
		if(M[id][5]!=D[2])
		{
			M[id][5]=D[2];
			score1change=true;
			tr.cells[4].style.backgroundColor="#bbbb22";
		}
		score2change=false;
		if(M[id][6]!=D[3])
		{
			M[id][6]=D[3];
			score2change=true;
			tr.cells[6+hasHandicapCol].style.backgroundColor="#bbbb22";
		}
		scorechange=score1change || score2change;	

		if(Config.redcard==1 && (D[6]!=M[id][9] || D[7]!=M[id][10]) && tr.style.display!="none")
		{
			hometeam=document.getElementById("HomeTeam_" + D[0]).innerHTML;
			guestteam=document.getElementById("GuestTeam_" + D[0]).innerHTML;
			if(document.all && !isIE10)
				sclassname=tr.cells[1].innerText;
			else
				sclassname=tr.cells[1].textContent;

			if(D[6]!=M[id][9]){				
				hometeam="<font color=red>" + hometeam +"</font>";
			}
			if(D[7]!=M[id][10]){
				guestteam="<font color=red>" + guestteam + "<font>";
			}	
			winStr+= "<tr bgcolor=#ffffff height=34 align=center class=line><td><font color=red>红牌</font></td><td> " +sclassname + "</td><td><b>"+ hometeam +"</b></td><td style='font-size: 18px;font-family:Verdana;font-weight:bold;'>" + D[6] + "-" + D[7] + "</td><td><b>" + guestteam +"</b></td></tr>";
			matchNum=matchNum+1;
		}//redcardChange

		if(scorechange || D[6]!=M[id][9] || D[7]!=M[id][10]) window.setTimeout("timecolors(" + id + ")",12000);
		
		//红牌变化了
		if(Config.redcard==1){
			if(D[6]!=M[id][9])
			{
				if(D[6]=="0")
					document.getElementById("HomeRed_" + D[0]).innerHTML="";
				else
					document.getElementById("HomeRed_" + D[0]).innerHTML= "<img src=/images/redcard" + D[6] + ".gif border='0'> "; 			
				tr.cells[4].style.backgroundColor="#ff8888";	
			}
			if(D[7]!=M[id][10])
			{
				if(D[7]=="0")
					document.getElementById("GuestRed_" + D[0]).innerHTML="";
				else
					document.getElementById("GuestRed_" + D[0]).innerHTML= "<img src=/images/redcard" + D[7] + ".gif border='0'> "; 			
				tr.cells[6+hasHandicapCol].style.backgroundColor="#ff8888";			
			}			
		}		
		M[id][7]=D[4];//半场比分
		M[id][8]=D[5];
		M[id][9]=D[6];//黄牌
		M[id][10]=D[7];

		//开赛时间
		if(M[id][1]!=D[8]){
		    if(typeof(SaleCount)!="undefined")
		    	tr.cells[2].innerHTML=D[8];
		    else
				tr.cells[2].innerHTML=D[14]+" " +D[8];
			M[id][1]=D[8];
		}
		var t = D[9].split(",");
		var t2 = new Date(t[0],t[1],t[2],t[3],t[4],t[5]);
		M[id][2]=t2;

		//状态
		if(M[id][4]!= D[1])
		{
			M[id][4]=D[1];
			switch(M[id][4])
			{
			case 1:
					goTime = Math.floor((new Date()-M[id][2]-difftime)/60000);
					if(goTime>45) goTime = "45+"
					if(goTime<1) goTime = "1";
					tr.cells[3].innerHTML = goTime + "<img src='/images/in.gif'>";
					break;
			case 3:
					goTime = Math.floor((new Date()-M[id][2]-difftime)/60000)+46;
					if(goTime>90) goTime = "90+";
					if(goTime<46) goTime = "46";
					tr.cells[3].innerHTML = goTime + "<img src='/images/in.gif'>";
					break;
			default:
					tr.cells[3].innerHTML=MatchState(D[1]);
					break;
   			}
   			if(M[id][4]==-1){
   			    var ResultType=document.getElementById("SelectResultType");
   			    if(ResultType) LotteryResult2(ResultType.options[ResultType.selectedIndex].value,id);
   			}
		}

		//score
		switch(M[id][4])
		{
			case 0:
			case -11:
			case -14:
				tr.cells[5+hasHandicapCol].innerHTML="-";
				if(!getByID("Page2")) tr.cells[7+hasHandicapCol].innerHTML="-";
				break;
			case 1:			
				tr.cells[5+hasHandicapCol].innerHTML=M[id][5] + "-" + M[id][6];
				break;
			default:  //2 3 -1 -12 -13			
				tr.cells[5+hasHandicapCol].innerHTML=M[id][5] + "-" + M[id][6];
				if(!getByID("Page2")) tr.cells[7+hasHandicapCol].innerHTML=M[id][7] + "-" + M[id][8];
				break;
		}
		if(M[id][4]>0 && M[id][4]<=3) 
		    tr.cells[5+hasHandicapCol].style.color="blue";
		else
		    tr.cells[5+hasHandicapCol].style.color="red";
		
		
		if(scorechange && Config.goalNotify==1)
		{
			if(tr.style.display!="none"){
    			ShowFlash(id);
				hometeam=document.getElementById("HomeTeam_" + D[0]).innerHTML;
				guestteam=document.getElementById("GuestTeam_" + D[0]).innerHTML;
				if(document.all && !isIE10)
					sclassname=tr.cells[1].innerText;
				else
					sclassname=tr.cells[1].textContent;
				if(score1change){				
					hometeam="<font color=red>" + hometeam +"</font>";
					score1="<font color=red>" + D[2] +"</font>";
					score2="<font color=blue>" + D[3] +"</font>";			
				}
				if(score2change){
					guestteam="<font color=red>" + guestteam + "<font>";
					score1="<font color=blue>" + D[2]+"</font>";
					score2="<font color=red>" + D[3] +"</font>";
				}	

				if(D[1]>=-1){
					if(matchNum % 2==0)
						winStr+= "<tr bgcolor=#ffffff height=34 align=center class=line><td><font color=#1705B1>" + sclassname +"</font></td><td> " + tr.cells[3].innerHTML + "</td><td><b>"+ hometeam +"</b></td><td width=11% style='font-size: 18px;font-family:Verdana;font-weight:bold;'>" + score1 + "-" + score2 + "</td><td><b>" + guestteam +"</b></td></tr>";
					else
						winStr+= "<tr bgcolor=#FDF1E7 height=34 align=center class=line><td><font color=#1705B1>" + sclassname +"</font></td><td> " + tr.cells[3].innerHTML + "</td><td><b>"+ hometeam +"</b></td><td width=11% style='font-size: 18px;font-family:Verdana;font-weight:bold;'>" + score1 + "-" + score2 + "</td><td><b>" + guestteam +"</b></td></tr>";
						
					matchNum=matchNum+1
				}
			}
		}//scorechange
		if (M[id][25] != undefined && M[id][25] != D[15] && document.getElementById("Explain_" + M[id][0]) != null) {
		    M[id][25] = D[15];
		    if (M[id][25] != "") { //赛事说明
		        getByID("Explain_" + M[id][0]).innerHTML = "<td colspan=13>" + showExplain(M[id][25], M[id][17], M[id][20], M[id][23]) + "</td><td style='display:none;'></td><td></td>";
		        if (getByID("row_" + M[id][16]).style.display == "") getByID("Explain_" + M[id][0]).style.display = "";
		    }
		}
    }
	if(matchNum>0) ShowCHWindow(winStr,matchNum);
}

function ShowFlash(id){
	try{
		if(Config.goalNotify==1 && M[id][4]>=-1){
			if(document.getElementById("row_" + id).style.display!="none"){
			   document.getElementById("flashsound").innerHTML="<object classid='clsid:D27CDB6E-AE6D-11cf-96B8-444553540000' codebase='http://download.macromedia.com/pub/shockwave/cabs/flash/swflash.cab#version=6,0,0,0' width='1' height='1'><param name='movie' value='/info/match/images/score.swf'><param name='quality' value='high'><param name='wmode' value='transparent'><embed src='/info/match/images/score.swf' quality='high' pluginspage='http://www.macromedia.com/go/getflashplayer' type='application/x-shockwave-flash' width='1' height='1'></embed></object>";
			}
		}
	}catch(e){};
}

function timecolors(matchid){
	try{
		var tr=document.getElementById("row_" + matchid);
		tr.cells[4].style.backgroundColor="";
		tr.cells[6+hasHandicapCol].style.backgroundColor="";
	}
	catch(e){}
}


//SP值自动更新
var oXmlHttpSP = zXmlHttp.createRequest();
var lastSpValue="";

function updateSP(type)
{
	try{
		if(SaleCount>0){
			initPoly();
			var urlString = "/data/" + type +".txt";
			oXmlHttpSP.open("get",urlString +"?t=" + Date.parse(new Date()),true);
			oXmlHttpSP.onreadystatechange = SpRefresh;			
			oXmlHttpSP.send(null);
		}
	}
	catch(e){}	
	window.setTimeout("updateSP("+type+")" , 60000);
}

function SpRefresh()
{
  try{
	if(oXmlHttpSP.readyState!=4 || (oXmlHttpSP.status!=200 && oXmlHttpSP.status!=0)) return;
	if(oXmlHttpSP.responseText=="" || oXmlHttpSP.responseText==lastSpValue) return;
	lastSpValue=oXmlHttpSP.responseText;
  	var sps = lastSpValue.split(';');
	UpDateSPValue(sps,0)
  }
  catch(e){}	
}

function UpDateSPValue(sps,i)
{
//	var sp = sps[i].split(',');
//	var v = document.getElementById("sp_"+ sp[0]);
//	if(v!=null){
//		var str = v.innerHTML.toLowerCase();
//		str = str.replace("<font color=#0000ff>↓</font>", "");
//		str = str.replace("<font color=#ff0000>↑</font>", "");
//		var value = new Number(str);//旧
//		var spv = new Number(sp[1]);//新
//		if(value > spv){
//			v.innerHTML = sp[1] + "<font color=#0000ff>↓</font>";
//		}else if(value < spv){
//			v.innerHTML = sp[1] + "<font color=#ff0000>↑</font>";
//		}else if(value == spv){
//			v.innerHTML = sp[1];
//		}
//	}
//	i++;
//	if(i<sps.length) setTimeout(function(){UpDateSPValue(sps,i);}, 1); 
//	
	
	var sp = sps[i].split(',');
	var v = document.getElementById("sp_"+ sp[0]);
	if(v!=null) v.innerHTML = sp[1];
	v = document.getElementById("sp2_"+ sp[0]);
	if(v!=null) v.innerHTML = sp[1];
	i++;
	if(i<sps.length) setTimeout(function(){UpDateSPValue(sps,i);}, 1); 
}


function LotteryResult(typeID)
{
	for(var id=1;id<=MatchCount;id++){
        LotteryResult2(typeID,id);
	}
}
function LotteryResult2(typeID,id)
{
    try{
        var result="";
	    var row=document.getElementById("row_"+ id);
		if(M[id][4]==-1){  //完场	
            if(typeID == 5){
                var polygoal=parseFloat(row.getAttribute("polygoal"));
                if (M[id][5]+polygoal > M[id][6]) result += "胜";
                else if (M[id][5]+polygoal == M[id][6]) result += "平";
                else result += "负";
            }
            if (typeID == 6)
            {   
                var score=M[id][5]+M[id][6];
                if (score >= 7) result = "7+";
                else result=score.toString();
            }
            if (typeID == 7)
            {   
                if(M[id][5] + M[id][6]>= 3) result="上";
                else result="下";
                if((M[id][5] + M[id][6]) % 2==0) result+="双";
                else result+="单";
            }
            if (typeID == 8)
            {   
                result=M[id][5]+":"+M[id][6];
                if(M[id][5]>M[id][6] & (M[id][5]>4 || M[id][6]>2)) result="<span style='font-weight:normal'>胜其它</span>" ;
                if(M[id][5]==M[id][6] & M[id][5]>=4) result="<span style='font-weight:normal'>平其它</span>" ;
                if(M[id][5]<M[id][6] & (M[id][5]>2 || M[id][6]>4)) result="<span style='font-weight:normal'>负其它</span>" ;
            }
            if (typeID == 9)
            {
                if (M[id][7] > M[id][8]) result = "胜";
                else if (M[id][7] == M[id][8]) result = "平";
                else result= "负";

                if (M[id][5] > M[id][6]) result += "胜";
                else if (M[id][5] == M[id][6]) result += "平";
                else result += "负";
            }
             
            row.cells[11].innerHTML=result;            
		}
    }catch(e){}
}

function HiddenSelected(value){
    var hh=parseInt(document.getElementById("hide_num").innerHTML);
    for(var i=1;i<=MatchCount;i++){
        var obj=document.getElementById("row_" +  M[i][16]);
	    if(obj.style.display==""){
	        if(document.getElementById("chk_" +  M[i][16]).checked==value){
    		    obj.style.display="none";
	 	        hh=hh+1;
	 	    }
	    }
	}
	document.getElementById("hide_num").innerHTML=hh;
}

var hideChoose = ",";
function onlyChooseShow(obj){
	initPoly() ;
	var isChecked = obj.checked;
	var num=0;
	var oriChoose = hideChoose;
	hideChoose = ",";
	for(var i=1;i<=MatchCount;i++){
		if(!getByID("row_"+i)) continue;
		if(isChecked){
			if (matrix[i][0] > 0) {
				if(oriChoose.indexOf(","+i+",")!= -1) getByID("row_"+i).style.display = "";
				else if(getByID("row_"+i).style.display == "none") num++;
			}
			else
			{
				if(getByID("row_"+i).style.display != "none"){
					getByID("row_"+i).style.display = "none";
					if(getByID("tr_"+i)) getByID("tr_"+i).style.display = "none";
					if(getByID("sp_"+i)) getByID("sp_"+i).className = "opensp";
					hideChoose += i+","
				}
				num++;
			}
		}
		else
		{
			if(oriChoose.indexOf(","+i+",")!= -1) getByID("row_"+i).style.display = "";
			else if(getByID("row_"+i).style.display == "none") num++;
		}
	}
	
	getByID("hide_num").innerHTML=num;
}