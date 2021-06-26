from PyQt5.QtWidgets import QApplication, QMainWindow,QFileDialog
from PyQt5.QtCore import QUrl
import sys
import design
from PyQt5 import QtWebKit
import os
import re
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QMessageBox
import datetime
from dateutil import parser
from nltk.tokenize import TweetTokenizer
from collections import OrderedDict,Counter
import unicodedata
import json
import string
import numpy as np
from gnarratives import Geonarrative,Word
#from shapely.geometry import Point, mapping
#import fiona
#from fiona.crs import from_epsg
from simplekml import Kml
import csv
#from pyproj import Proj, transform
import osgeo.ogr as ogr
import osgeo.osr as osr
import gdal
import pickle
from numpy.core import multiarray
timepattern=re.compile('^(?:(?:([01]?[0-9]|2[0-3]):)([0-5]?[0-9]):)([0-5]?[0-9])$')
prjdat='GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
class WordmapperApp(QMainWindow, design.Ui_MainWindow):
    def __init__(self, parent=None):
        super(WordmapperApp, self).__init__(parent)
        self.setupUi(self)
        self.geonarratives=[]
        self.stopwords=[]
        cwd = os.getcwd()
        self.webView.settings().setAttribute(QtWebKit.QWebSettings.PluginsEnabled, True)
        self.webView.load(QUrl('file:///'+cwd+'/working/WordMapper.html'))
        self.webView.loadFinished.connect(self.finishLoading)
        self.folder=None
    #to browse a geonarrative file
    @pyqtSlot(result=str)
    def browse_geonarrative(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Narrative",
                '', "Narratives (*.txt)")
        if(not fileName):
            fileName=""
        return fileName
    #to browse a gps file  
    @pyqtSlot(result=str)
    def browse_gps(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open GPS",
                '', "GPS (*.csv)")
        if(not fileName):
            fileName=""
        return fileName
    #to browse a folder
    @pyqtSlot(result=str)
    def browse_folder(self):
        fileName = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
        if( not fileName):
            fileName=""
        self.folder=fileName
        return fileName   
    #upload a geonarrative, should do validations before proceeding  
    @pyqtSlot('QVariantMap',result=str)
    def upload(self,upload):
        gnarrfile,csvfile,timeutc,folder,senttimevals=upload['gnarrfile'].strip(),upload['gpsfile'].strip(),upload['offset'].strip(),upload['folder'].strip(),upload['senttime'].strip()
        if not gnarrfile or not csvfile or not timeutc or not folder:
            #one of the required textbox is missing,don't process
            return "geonarrative file,csv file,time in utc and outputfolder is mandatory"
        if not os.path.isfile(gnarrfile) or not os.path.isfile(csvfile):
            #one of the necessary file doesn't exist
            return "geonarrative file,csv file,time in utc and outputfolder is mandatory"
        if not timepattern.match(timeutc.strip()) or self.converttimestringtotime(timeutc.strip()) is None:
            return "The utc time should be in hh:mm:ss format"
        #sentence time in seconds
        senttime=60
        if senttimevals:
            try:
               senttime=int(senttimevals)
            except:
                #if there is an exception default to 60 seconds
                senttime=60
        filenarrative=open(gnarrfile)   
        filecsv=open(csvfile)       
        narrativelist=[]
        startindex=0
        filecsv.readline()
        csvdata=filecsv.readlines()
        #offset time
        timestringformatteddate=parser.parse(csvdata[0].split(',')[1],fuzzy=True).replace(hour=int(timeutc.split(':')[0]),minute=int(timeutc.split(':')[1]),second=int(timeutc.split(':')[2]))
        #offset index for CSV
        csvstartindex=0
        #calculate the offset index. The offset index identifies the starting row for GPS data
        for dat in csvdata:
            if timestringformatteddate>parser.parse(dat.split(',')[1],fuzzy=True):
                csvstartindex+=1
                continue
            else:
                break
        linenumber=0
        outofsequence=False
        outofsequencedata=[]
        errormessage=None
        for lines in filenarrative:
            #replace the iso line break character
            lines=lines.replace('\xa0',' ').strip()
            #replace the unwanted tab character also
            lines=lines.replace('\t',' ').strip()
            #if line has no text skip
            if lines.isspace():
                linenumber+=1
                continue
            timestamp=None
            text=None
            #Split the sentence to tokens of words
            linetokens=lines.split()
            if len(linetokens)==0:
                linenumber+=1
                continue
            #token that might have time
            possibtimetoken=linetokens[0]
            #we must remove [] if it exsits from the possible time token
		 # replace '[]()'
            normalizedtoken=possibtimetoken.replace('[',' ').replace(']',' ').replace('(',' ').replace(')',' ').split()[0]
            #if time is of the form mm:ss (08:50), then don't process
            if len(normalizedtoken.split(':'))==2:
                #possible malformed date
                errormessage="Error at line number "+str(linenumber+1)+"\n"+lines
                break
            #if time is of the form hh:mm:ss try converting to timestamp
            elif len(normalizedtoken.split(':'))==3:
                timestamp=self.converttimestringtotime(normalizedtoken)
                #if timestamp is in wrong format we should stop
                if timestamp is None:
                    #possible malformed date
                    errormessage="Error at line number "+str(linenumber+1)+"\n"+lines
                    break
                #split to remove ] or space and extract text alone
                else:
                    if ']' in possibtimetoken:
                        text=' ' if len(lines.split(']',1))<2 else lines.split(']',1)[1]
                    else:
                        text=' ' if len(lines.split(' ',1))<2 else lines.split(' ',1)[1]
            #if there is no time stamp, treat it as continuing text from last line
            else:
                text=lines
            if timestamp is None:
                #if there is no time stamp and if its start of line then we should not process
                if len(narrativelist)==0:
                    #no timestamp at first line itself no need to process
                    errormessage="No time stamp at first line \n"+lines
                    break
                #if there is text only, append it to the last timestamp text
                else:
                    narrativelist[len(narrativelist)-1][1]+=" "+text
            
            else:
                timeinseconds=(timestamp.hour*3600)+(timestamp.minute*60)+timestamp.second
                #value indicating whether the sentence has gps coordinate associated with it
                withingps=1
                indexincsv=csvstartindex
                if len(narrativelist)!=0:
                    indexincsv=csvstartindex+timeinseconds-(narrativelist[0][0])
                #if narrative crosses over gps data then we should indicate that in gps value flag
                if indexincsv>len(csvdata)-1:
                    withingps=0
                #the narrative list contains the time in seconds, the real timestamp in the narrative, the flag indicating whether sentence is with in GPS
                narrativelist.append([timeinseconds,text,normalizedtoken,withingps,"Default"])
                #if the succeeding timestamp is less than current then we should treat it as out of sequence and store it to display to user
                if len(narrativelist)>1 and timeinseconds<=narrativelist[len(narrativelist)-2][0]:
                    outofsequence=True
                    outofsequencedata.append([linenumber+1,lines])
            linenumber+=1
        if errormessage: 
            return errormessage
        if outofsequence:
            message=""
            for dat in outofsequencedata:
                message+="Line "+str(dat[0])+":"+str(dat[1])+"\n"
            return message
        worddict=OrderedDict()
        tokenparser=TweetTokenizer()
        #go through narrative data line by line
        for ind in range(len(narrativelist)):
            #if there is nothing in the line other than time stamp, skip
            if len(narrativelist[ind][1].strip())==0:
                continue
            #normalize unwanted characters
            #wordtokens=tokenparser.tokenize(unicodedata.normalize('NFKD', narrativelist[ind][1].decode('windows-1252').replace(u'\u2019',"'")).encode('ascii','ignore'))
            #wordtokens=tokenparser.tokenize(narrativelist[ind][1])
            wordtokens=tokenparser.tokenize(unicodedata.normalize('NFKD', narrativelist[ind][1]).replace(u'\u2019',"'"))
            wordtokenpunctremoved=[]
            for wrds in wordtokens:
                if len(wrds.strip(string.punctuation).strip())!=0:
                    wordtokenpunctremoved.append(wrds.strip(string.punctuation).strip())
            #if there are only punctuations in a string do we need to store it
            if len(wordtokenpunctremoved)==0:
                continue
            #start and end time for interpolation
            start,end=narrativelist[ind][0]-(narrativelist[0][0]),0
            #since last sentence doesn't have an end timestamp, we use sentence time for interpolation
            if ind!=len(narrativelist)-1:                
                end=start+min((narrativelist[ind+1][0]-narrativelist[ind][0]),senttime)
            else:
                end=start+senttime
            wordseconds=np.linspace(start,end,num=len(wordtokenpunctremoved)+1)
            for j in range(len(wordtokenpunctremoved)):
                #value indicating whether word is with in GPS limits
                ingps=1
                startindex,endindex=int(csvstartindex+np.floor(wordseconds[j])),int(csvstartindex+np.ceil(wordseconds[j+1]))
                #if start index itself is out of gps range then assign start index and end index to be of last two gps coordinates. Also change value to indicate these are not with in GPS
                if startindex>=len(csvdata)-1:
                    ingps=0
                    startindex,endindex=len(csvdata)-2,len(csvdata)-1
                #if the end index has crossed over the gps data, assign it to the last gps record and change value to indicate these are not with in GPS
                elif endindex>len(csvdata)-1:
                    ingps=0
                    endindex=len(csvdata)-1
                lonlow,latlow=float(csvdata[startindex].split(',')[3]),float(csvdata[startindex].split(',')[2])
                lonhigh,lathigh=float(csvdata[endindex].split(',')[3]),float(csvdata[endindex].split(',')[2])
                #interpolation alg
                lowhighdistshift=np.sqrt((np.power(lonlow-lonhigh,2))+(np.power(lathigh-latlow,2)))
                lowhightimeshift=endindex-startindex
                currtimeshift=wordseconds[j+1]-wordseconds[j]
                currdistshift=(currtimeshift*lowhighdistshift)/lowhightimeshift
                if (lonhigh-lonlow)==0:
                    xshift=np.inf
                else:
                    xshift=lonhigh-lonlow
                slopeangleradians=np.arctan((lathigh-latlow)/xshift)
                loncurr=lonlow+(currdistshift*np.cos(slopeangleradians))
                latcurr=latlow+(currdistshift*np.sin(slopeangleradians))
                wrd=Word()
                wrd.coordinates=[loncurr,latcurr]
                wrd.text=wordtokenpunctremoved[j]
                wrd.index_narrative=ind
                wrd.withingps=ingps
                if ind in worddict:
                    worddict[ind].append(wrd)
                else:
                    worddict[ind]=[wrd]
            worddict[ind]=np.asarray(worddict[ind])
        geonarr=Geonarrative()
        geonarr.categories=[]
        geonarr.gpsdata=csvdata
        geonarr.offsettime=timeutc
        geonarr.interpolationtime=str(senttime)
        geonarr.narrativefilename=os.path.basename(gnarrfile)
        geonarr.gpsfilename=os.path.basename(csvfile)
        geonarr.narrativedata=narrativelist
        geonarr.worddict=worddict
        geonarr.offset=csvstartindex
        self.geonarratives.append(geonarr)
        self.updateNarrativeDropDown(gnarrfile)
        return "The files were successfully processed"
    def converttimestringtotime(self,timestring):
        timedat=None
        try:
            timedat=datetime.datetime.strptime(timestring,"%H:%M:%S")
        except:
            print ("Error occured")
        return timedat 
    
    def updateNarrativeDropDown(self,narrfile):
        index=len(self.geonarratives)-1
        narrative=os.path.basename(narrfile).split('.')[0]
        command = ('updateDropDown("'+narrative+'",'+str(index)+');')
        self.webView.page().mainFrame().evaluateJavaScript(command)

    @pyqtSlot(result=str)
    def getInitialStopWords(self):
        cwd=os.getcwd()
        if os.path.isfile(cwd+"/stopwords.txt"):
            stopwords=[wrd.lower() for wrd in open(cwd+"/stopwords.txt").read().split('\n')]
            self.stopwords=stopwords
            return ",".join(stopwords)
        
    @pyqtSlot()
    def finishLoading(self):
        self.webView.page().mainFrame().addToJavaScriptWindowObject("wm", self)

    @pyqtSlot(int,str,int)
    def updatecategforsent(self,idval,categval,index):
        self.geonarratives[index].narrativedata[idval][4]=categval
        
    @pyqtSlot('QVariantMap',result=str)
    def getSearchIndexes(self,searchquery):
        indexes=[]
        wordindexes=[]
        data={'ind':indexes,"topwords":[],"wordindexes":wordindexes}
        geonarrative=self.geonarratives[int(searchquery['narrindex'])]
        searchwordsarray=searchquery['words']
        typeval=searchquery['type']
        for key in geonarrative.worddict:
            if int(searchquery['categselected'])==1:
                if geonarrative.narrativedata[key][4] not in searchquery['selectedcategs']:
                    continue
                #if we don't have a search query and we have eligible indexes then this is a type of query to just filter out categories
                elif len(searchwordsarray)==0:
                    indexes.append(key)
                    continue
            lowercasewords=np.array([x.lower() for x in [k.text for k in geonarrative.worddict[key]]])
            indexval=0
            wordindex=[]
            for swords in searchwordsarray:
                wordregex='^'+swords.lower().replace('*','.*')+'$'
                regexval=re.compile(wordregex)
                vmatch = np.vectorize(lambda x:bool(regexval.match(x)))
                arr_indexes = np.where(vmatch(lowercasewords))
                if len(arr_indexes[0])!=0:
                    indexval+=1
                    wordindex.extend(arr_indexes[0].tolist())
            if indexval!=0:
                if typeval=='or' or indexval==len(searchwordsarray):
                    indexes.append(key)
                    wordindexes.append(list(set(wordindex)))
        if len(indexes)>0:
            searched=[list(geonarrative.worddict[i]) for i in indexes]
            allwords = [wrd.text.lower() for words in searched for wrd in words if wrd.text.lower() not in self.stopwords and len(wrd.text)>=3]
            counterdata=Counter(allwords)
            top100=counterdata.most_common(100)
            for d in top100:
                data["topwords"].append({'word':d[0],'count':d[1]})
        return json.dumps(data)
    def getTransformedCoordinates(self,coord,inepsg,outepsg):
        inProj = Proj(init='epsg:'+str(inepsg))
        outProj = Proj(init='epsg:'+str(outepsg))
        x2,y2 = transform(inProj,outProj,coord[0],coord[1])
        return [x2,y2]
    @pyqtSlot('QVariantMap',result=str)
    def getSpatialWordCloudWords(self,searchquery):
        coords=list(reversed(list(map(float,searchquery['coords'].split(',')))))
        geonarrative=self.geonarratives[int(searchquery['narrindex'])]
        allwords=[]
        data={"topwords":[]}
        for key in geonarrative.worddict:
            for words in geonarrative.worddict[key]:
                if np.linalg.norm(np.asarray(self.getTransformedCoordinates(coords,4326,3857))-np.asarray(self.getTransformedCoordinates(words.coordinates,4326,3857)))<=float(searchquery['radius']) and words.text.lower() not in self.stopwords and len(words.text)>=3:
                    allwords.append(words.text.lower())
        counterdata=Counter(allwords)
        top100=counterdata.most_common(100)
        for d in top100:
            data["topwords"].append({'word':d[0],'count':d[1]})
        return json.dumps(data)
        
    @pyqtSlot('QVariantMap',result=str)
    def downloadThemes(self,themedata):
        geonarrative=self.geonarratives[int(themedata['index'])]
        filename=themedata['filename']
        data=themedata['themes']
        datadict={}
        for dat in data:
            datadict[int(dat[-1])]=dat[:-1]
        if int(themedata['isselected'])==1:
            keys=list(map(int,themedata['searchind']))
        else:
            keys=geonarrative.worddict.keys()
        driver = ogr.GetDriverByName("ESRI Shapefile")
        data_source = driver.CreateDataSource(self.folder+"//"+filename+".shp")
        prjfile=open(self.folder+"//"+filename+".prj",'w')
        prjfile.write(prjdat)
        prjfile.close()
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        layer = data_source.CreateLayer("themes", srs, ogr.wkbPoint)
        id_ = ogr.FieldDefn("id", ogr.OFTInteger)
        layer.CreateField(id_)
        sentence=ogr.FieldDefn("sentence", ogr.OFTString)
        sentence.SetWidth(250)
        layer.CreateField(sentence)
        theme=ogr.FieldDefn("theme", ogr.OFTString)
        theme.SetWidth(150)
        layer.CreateField(theme)
        spatial = ogr.FieldDefn("spatial", ogr.OFTInteger)
        layer.CreateField(spatial)
        timestamp=ogr.FieldDefn("timestamp", ogr.OFTString)
        timestamp.SetWidth(150)
        layer.CreateField(timestamp)
        for ind in keys:
            sentenceindexingps=geonarrative.narrativedata[ind][0]-geonarrative.narrativedata[0][0]+geonarrative.offset
            if geonarrative.narrativedata[ind][3]==0:
                sentenceindexingps=len(geonarrative.gpsdata)-1
            lat,lng= float(geonarrative.gpsdata[sentenceindexingps].split(',')[2]),float(geonarrative.gpsdata[sentenceindexingps].split(',')[3])
            text=geonarrative.narrativedata[ind][1]
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField("id", ind)
            feature.SetField("sentence", text)
            feature.SetField("theme", datadict[ind][0])
            feature.SetField("spatial", int(datadict[ind][1]))
            feature.SetField("timestamp", geonarrative.narrativedata[ind][2])
            wkt = "POINT(%f %f)" %  ( lng,lat )
            point = ogr.CreateGeometryFromWkt(wkt)
            feature.SetGeometry(point)
            layer.CreateFeature(feature)
            feature = None
        data_source=None
        driver=None
        dschema = { 'geometry': 'Point', 'properties': { 'id': 'int','sentence':'str','theme':'str','spatial':'int' } }
        return "Themes Successfully Downloaded"
    
    @pyqtSlot('QVariantMap',result=str)
    def downloadKML(self,kmldata):
        geonarrative=self.geonarratives[int(kmldata['index'])]
        sentfile_name=self.folder+"//"+kmldata['filename']+"_sentence.kml"
        word_file_name=self.folder+"//"+kmldata['filename']+"_word.kml"
        redpinurl='http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png'
        yellowpinurl='http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png'
        purplepinurl='http://maps.google.com/mapfiles/kml/pushpin/purple-pushpin.png'
        sentkml=Kml()
        wordkml=Kml()
        themedata=kmldata['themes']
        themedatadict={}
        for dat in themedata:
            themedatadict[int(dat[-1])]=dat[:-1]
        searchindexes=list(map(int,kmldata['searchind']))
        wordindexes=kmldata['wordind']
        for i in range(len(wordindexes)):
            wordindexes[i]=list(map(int,wordindexes[i]))
        if int(kmldata['isselected'])==1:
            keys=searchindexes
        else:
            keys=geonarrative.worddict.keys()
        wrdcnt=0
        for ind in keys:
            sentenceindexingps=geonarrative.narrativedata[ind][0]-geonarrative.narrativedata[0][0]+geonarrative.offset
            if geonarrative.narrativedata[ind][3]==0:
                sentenceindexingps=len(geonarrative.gpsdata)-1
            lat,lng= float(geonarrative.gpsdata[sentenceindexingps].split(',')[2]),float(geonarrative.gpsdata[sentenceindexingps].split(',')[3])
            text=geonarrative.narrativedata[ind][2]+" "+geonarrative.narrativedata[ind][1]
            pnt=sentkml.newpoint(name=str(ind), coords=[(lng,lat)],description=text)
            if ind in searchindexes:
                pnt.style.iconstyle.icon.href =yellowpinurl
            else:
                if int(themedatadict[ind][1])==1:
                    pnt.style.iconstyle.icon.href=purplepinurl
                else:
                    pnt.style.iconstyle.icon.href=redpinurl
            for i in range(len(geonarrative.worddict[ind])):
                wrd=geonarrative.worddict[ind][i]
                wpnt=wordkml.newpoint(name=str(wrdcnt), coords=[(wrd.coordinates[0],wrd.coordinates[1])],description=wrd.text)
                wrdcnt+=1
                #wordindexes can be of zero length when the filter is based only on categs
                if ind in searchindexes and len(wordindexes)!=0 and i in wordindexes[searchindexes.index(ind)]:
                    wpnt.style.iconstyle.icon.href = yellowpinurl
                else:
                    wpnt.style.iconstyle.icon.href=redpinurl
        sentkml.save(sentfile_name) 
        wordkml.save(word_file_name)
        return "KML Successfully Downloaded"
    
    @pyqtSlot('QVariantMap',result=str)
    def downloadCSV(self,csvdata):
        geonarrative=self.geonarratives[int(csvdata['index'])]
        sentfile_name=self.folder+"//"+csvdata['filename']+"_sentence.csv"
        word_file_name=self.folder+"//"+csvdata['filename']+"_word.csv"
        searchindexes=list(map(int,csvdata['searchind']))
        wordindexes=csvdata['wordind']
        themedata=csvdata['themes']
        themedatadict={}
        for dat in themedata:
            themedatadict[int(dat[-1])]=dat[:-1]
        for i in range(len(wordindexes)):
            wordindexes[i]=list(map(int,wordindexes[i]))
        wrdcnt=0
        if int(csvdata['isselected'])==1:
            keys=searchindexes
        else:
            keys=geonarrative.worddict.keys()
        with open(sentfile_name, 'w',newline='',encoding='utf-8') as sentfile:
            with open(word_file_name, 'w',newline='',encoding='utf-8') as wordfile:
                sent_writer=csv.writer(sentfile)
                word_writer=csv.writer(wordfile)
                sent_writer.writerow(["id","text","longitude","latitude","selected","timestamp","category","spatial"])
                word_writer.writerow(["id","sent_id","text","longitude","latitude","selected","withingps","category","spatial"])
                for ind in keys:
                    sentenceindexingps=geonarrative.narrativedata[ind][0]-geonarrative.narrativedata[0][0]+geonarrative.offset
                    if geonarrative.narrativedata[ind][3]==0:
                        sentenceindexingps=len(geonarrative.gpsdata)-1
                    lat,lng= float(geonarrative.gpsdata[sentenceindexingps].split(',')[2]),float(geonarrative.gpsdata[sentenceindexingps].split(',')[3])
                    text=geonarrative.narrativedata[ind][1]
                    selected='N'
                    if ind in searchindexes:
                         selected='Y'
                    sent_writer.writerow([str(ind),text,str(lng),str(lat),selected,geonarrative.narrativedata[ind][2],themedatadict[ind][0],str(themedatadict[ind][1])])
                    for i in range(len(geonarrative.worddict[ind])):
                        wrd=geonarrative.worddict[ind][i]
                        sel='N'
                        #wordindexes can be of zero length when the filter is based only on categs
                        if ind in searchindexes and len(wordindexes)!=0 and i in wordindexes[searchindexes.index(ind)]:
                            sel='Y'  
                        word_writer.writerow([str(wrdcnt),str(ind),wrd.text,str(wrd.coordinates[0]),str(wrd.coordinates[1]),sel,str(wrd.withingps),themedatadict[ind][0],str(themedatadict[ind][1])])
                        wrdcnt+=1
        sentfile.close()
        wordfile.close()
        return "CSV Successfully Downloaded"
    
    @pyqtSlot(int,str,result=str)
    def downloadnarrative(self,index,name):
        geonarrative=self.geonarratives[index]
        with open(self.folder+"//"+name+".file", "wb") as f:
            pickle.dump(geonarrative, f, pickle.HIGHEST_PROTOCOL)
        return "Narrative Successfully Downloaded"
    
    @pyqtSlot('QVariantMap',result=str)
    def downloadShape(self,shapedata):
        driver = ogr.GetDriverByName("ESRI Shapefile")
        data_source_sentence = driver.CreateDataSource(self.folder+"//"+shapedata['filename']+"_sentence.shp")
        data_source_word = driver.CreateDataSource(self.folder+"//"+shapedata['filename']+"_word.shp")
        prjfile_word=open(self.folder+"//"+shapedata['filename']+"_word.prj",'w')
        prjfile_word.write(prjdat)
        prjfile_word.close()
        prjfile_sentence=open(self.folder+"//"+shapedata['filename']+"_sentence.prj",'w')
        prjfile_sentence.write(prjdat)
        prjfile_sentence.close()
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        layer_sent = data_source_sentence.CreateLayer("sent", srs, ogr.wkbPoint)
        layer_word = data_source_word.CreateLayer("word", srs, ogr.wkbPoint)
        id_s = ogr.FieldDefn("id", ogr.OFTInteger)
        layer_sent.CreateField(id_s)
        text_s=ogr.FieldDefn("text", ogr.OFTString)
        text_s.SetWidth(250)
        layer_sent.CreateField(text_s)
        sel_s=ogr.FieldDefn("selected", ogr.OFTString)
        sel_s.SetWidth(10)
        layer_sent.CreateField(sel_s)
        time_s=ogr.FieldDefn("timestamp", ogr.OFTString)
        time_s.SetWidth(30)
        layer_sent.CreateField(time_s)
        categ_s=ogr.FieldDefn("category", ogr.OFTString)
        categ_s.SetWidth(50)
        layer_sent.CreateField(categ_s)
        spatial_s=ogr.FieldDefn("spatial", ogr.OFTInteger)
        layer_sent.CreateField(spatial_s)
        id_w=ogr.FieldDefn("id", ogr.OFTInteger)
        layer_word.CreateField(id_w)
        id_w_s=ogr.FieldDefn("sent_id", ogr.OFTInteger)
        layer_word.CreateField(id_w_s)
        text_w=ogr.FieldDefn("text", ogr.OFTString)
        text_w.SetWidth(250)
        layer_word.CreateField(text_w)
        sel_w=ogr.FieldDefn("selected", ogr.OFTString)
        sel_w.SetWidth(10)
        layer_word.CreateField(sel_w)
        with_w=ogr.FieldDefn("withingps", ogr.OFTInteger)
        layer_word.CreateField(with_w)
        categ_w=ogr.FieldDefn("category", ogr.OFTString)
        categ_w.SetWidth(50)
        layer_word.CreateField(categ_w)
        spatial_w=ogr.FieldDefn("spatial", ogr.OFTInteger)
        layer_word.CreateField(spatial_w)
        geonarrative=self.geonarratives[int(shapedata['index'])]
        searchindexes=list(map(int,shapedata['searchind']))
        wordindexes=shapedata['wordind']
        themedata=shapedata['themes']
        themedatadict={}
        for dat in themedata:
            themedatadict[int(dat[-1])]=dat[:-1]
        for i in range(len(wordindexes)):
            wordindexes[i]=list(map(int,wordindexes[i]))
        if int(shapedata['isselected'])==1:
            keys=searchindexes
        else:
            keys=geonarrative.worddict.keys()
        wrdcnt=0
        for ind in keys:
            sentenceindexingps=geonarrative.narrativedata[ind][0]-geonarrative.narrativedata[0][0]+geonarrative.offset
            if geonarrative.narrativedata[ind][3]==0:
                sentenceindexingps=len(geonarrative.gpsdata)-1
            lat,lng= float(geonarrative.gpsdata[sentenceindexingps].split(',')[2]),float(geonarrative.gpsdata[sentenceindexingps].split(',')[3])
            text=geonarrative.narrativedata[ind][1]
            selected='N'
            if ind in searchindexes:
                selected='Y'
            feature = ogr.Feature(layer_sent.GetLayerDefn())
            feature.SetField("id", ind)
            feature.SetField("text", text)
            feature.SetField("selected", selected)
            feature.SetField("timestamp", geonarrative.narrativedata[ind][2])
            feature.SetField("category", themedatadict[ind][0])
            feature.SetField("spatial", int(themedatadict[ind][1]))
            wkt = "POINT(%f %f)" %  ( lng,lat )
            point = ogr.CreateGeometryFromWkt(wkt)
            feature.SetGeometry(point)
            layer_sent.CreateFeature(feature)
            feature = None
            for i in range(len(geonarrative.worddict[ind])):
                wrd=geonarrative.worddict[ind][i]
                sel='N'
                #wordindexes can be of zero length when the filter is based only on categs
                if ind in searchindexes and len(wordindexes)!=0 and i in wordindexes[searchindexes.index(ind)]:
                    sel='Y'
                feature = ogr.Feature(layer_word.GetLayerDefn())
                feature.SetField("id", wrdcnt)
                feature.SetField("sent_id", ind)
                feature.SetField("text", wrd.text)
                feature.SetField("selected", sel)
                feature.SetField("withingps", wrd.withingps)
                feature.SetField("category", themedatadict[ind][0])
                feature.SetField("spatial", int(themedatadict[ind][1]))
                wkt = "POINT(%f %f)" %  ( wrd.coordinates[0],wrd.coordinates[1])
                point = ogr.CreateGeometryFromWkt(wkt)
                feature.SetGeometry(point)
                layer_word.CreateFeature(feature)
                feature = None
                wrdcnt+=1
        data_source_sentence=None
        data_source_word=None
        driver=None
        return "Shape Files Successfully Downloaded"
    
    @pyqtSlot(int, result=str)
    def publishNarrativeData(self,selindex):
        gnarrative=self.geonarratives[selindex]
        outdat={"data":[],"topwords":[],"path":[],"categories":gnarrative.categories,"defaultcategory":gnarrative.defaultcode}
        allwords = [wrd.text.lower() for words in gnarrative.worddict.values() for wrd in words if wrd.text.lower() not in self.stopwords and len(wrd.text.lower())>=3]
        counterdata=Counter(allwords)
        top100=counterdata.most_common(100)
        for d in top100:
            outdat["topwords"].append({'word':d[0],'count':d[1]})
        for ind in gnarrative.worddict:
            sentenceindexingps=gnarrative.narrativedata[ind][0]-gnarrative.narrativedata[0][0]+gnarrative.offset
            if gnarrative.narrativedata[ind][3]==0:
                sentenceindexingps=len(gnarrative.gpsdata)-1
            lat,lng= float(gnarrative.gpsdata[sentenceindexingps].split(',')[2]),float(gnarrative.gpsdata[sentenceindexingps].split(',')[3])
            text=gnarrative.narrativedata[ind][1]
            outdat["data"].append([lat,lng,text,ind,gnarrative.narrativedata[ind][4]])
        #real path
        outdat["path"]=[[float(dat.split(',')[2]),float(dat.split(',')[3])] for dat in gnarrative.gpsdata]
        return json.dumps(outdat)
   
    @pyqtSlot(str)
    def updatestopwords(self,stopwordstring):
        self.stopwords=stopwordstring.split(",")

    @pyqtSlot(str,int)
    def addcateg(self,categval,index):
        self.geonarratives[index].categories.append(categval)
        
    @pyqtSlot(result=str)
    def readsearchwords(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Search Words File, Words should be line by line",
                '', "Search Words (*.txt)")
        results=""
        if fileName:
            wordfile=open(fileName)
            worddatarray=[]
            for wrd in wordfile:
                if wrd.isspace():
                    continue
                worddatarray.append(wrd.strip())
            results+=",".join(worddatarray)
        return results
    @pyqtSlot(result=str)
    def loadstopwords(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Stop Words File, Words should be line by line",
                '', "Stop Words (*.txt)")
        results=""
        if fileName:
            wordfile=open(fileName)
            worddatarray=[]
            for wrd in wordfile:
                if wrd.isspace():
                    continue
                worddatarray.append(wrd.strip())
            results+=",".join(worddatarray)
        return results

    @pyqtSlot(int,str,result=str)
    def getupdatedtopwords(self,narrind,indexstring):
        topwords=[]
        gnarrative=self.geonarratives[narrind]
        if len(indexstring)==0:
            indexes=gnarrative.worddict.keys()
        else:
            indexes=list(map(int,indexstring.split(',')))
        searched=[list(gnarrative.worddict[i]) for i in indexes]
        allwords = [wrd.text.lower() for words in searched for wrd in words if wrd.text.lower() not in self.stopwords and len(wrd.text)>=3]
        counterdata=Counter(allwords)
        top100=counterdata.most_common(100)
        for d in top100:
            topwords.append({'word':d[0],'count':d[1]})
        return json.dumps(topwords)

    @pyqtSlot('QVariantMap',str,result=str)
    def downloadinfo(self,info,filename):
        gnarrative=self.geonarratives[int(info['narrid'])]
        out_file=open(self.folder+"//"+filename+".txt",'w')
        out_file.write('Narrative File: '+gnarrative.narrativefilename+"\n")
        out_file.write('GPS File: '+gnarrative.gpsfilename+"\n")
        out_file.write('Offset: '+gnarrative.offsettime+"\n")
        out_file.write('Sentence time: '+gnarrative.interpolationtime+"\n")
        if self.stopwords is None:
            stpwrds=""
        else:
            stpwrds=",".join(self.stopwords)
        out_file.write('Stopwords: '+stpwrds+"\n")
        out_file.write('Keywords: '+",".join(info['searchwords'])+"\n")
        out_file.write('Categories: '+",".join(info['categories'])+"\n")
        out_file.close()
        return "info downloaded"

    @pyqtSlot('QVariantMap',int)
    def categoryremovedupdate(self,categdata,index):
        self.updatedefaultcategory(categdata['defaultcode'],index)
        self.removecategories(categdata['selected'],index)
        self.updateeachnarrativecategories(categdata['categforsentence'],index)
        
    @pyqtSlot(str,int)
    def updatedefaultcategory(self,defcode,index):
        self.geonarratives[index].defaultcode=defcode

    @pyqtSlot('QVariantList',int)
    def removecategories(self,categories,index):
        self.geonarratives[index].categories=[e for e in self.geonarratives[index].categories if e not in categories]

    @pyqtSlot('QVariantList',int)
    def updateeachnarrativecategories(self,indexdata,index):
        datadict={}
        for dat in indexdata:
            datadict[dat[0]]=dat[1]
        gnarrative=self.geonarratives[index]
        for ind in gnarrative.worddict:
            gnarrative.narrativedata[ind][4]=datadict[ind]

    @pyqtSlot('QVariantMap',int)
    def categoryupdatedefault(self,categdata,index):
        self.updatedefaultcategory(categdata['defaultcode'],index)
        self.updateeachnarrativecategories(categdata['categforsentence'],index)

    @pyqtSlot(result=str)
    def uploadexisting(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Narrative File",
                '', "File (*.file)")
        if not fileName:
            return "No file Loaded"
        with open(fileName, "rb") as f:
            geonarr=pickle.load(f)
            self.geonarratives.append(geonarr)
            self.updateNarrativeDropDown(fileName)
        return "Succesfully added the narrative"
def main():
    app = QApplication(sys.argv)
    form = WordmapperApp()
    form.show()
    app.exec_()

if __name__ == '__main__':              # if we're running file directly and not importing it
    main()                              # run the main function
