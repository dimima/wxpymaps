#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    This file is part of wxpymaps.
#
#    wxpymaps is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    wxpymaps is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with wxpymaps.  If not, see <http://www.gnu.org/licenses/>.

import os
import math
import thread
import Queue
import wx
import  wx.lib.newevent
from wx.lib.buttons import GenBitmapButton, GenBitmapToggleButton


import globalmaptiles
import marker_dialog
import path_dialog
import urllib
from PIL import Image
from threading import Timer
from xml.dom.minidom import Document


baseurlmap={0: "http://mt1.google.com/vt/lyrs=m@132&hl=en",#default
    1: "http://mt1.google.com/vt/lyrs=t",
    2: "http://mt1.google.com/vt/lyrs=p",
                   
    #mappe satellitari
    3: "http://mt1.google.com/vt/lyrs=s",

    #mappe satellitari con strade
    4: "http://mt1.google.com/vt/lyrs=y",

    #overlay:
    5: "http://mt1.google.com/vt/lyrs=h",
    6: "http://mt1.google.com/vt/lyrs=r"
}

APP_NAME = "Application"
MAP_TYPE=0 #numero tra 0 e 6
DIR_CACHE = os.getcwd()+"/cache/"+str(MAP_TYPE)+"/"
DOWNLOAD_THREAD_NUM =3
QUEUE_WAIT = 0.5


#coda di tipo LIFO: se cambio livello di zoom vengono inseriti nella coda tile 
#relativi al nuovo livello di zoom, voglio che vengano mostrati prima questi
tile_to_download = Queue.LifoQueue(maxsize=0)


class Tile:
    """
    Classe che definisce una tile
    """
    
    def __init__(self, x, y, zoom):
        self.tile = x, y, zoom
        self.id = wx.NewId()


    def loadtile(self):
        """
        se esiste (non corrotta) restituisce l'immagine riferita al tile
        """
        x, y, zoom = self.tile
        filename = DIR_CACHE+"/"+str(x)+"-"+str(y)+"-"+str(zoom)+".png"
        if (os.path.exists(filename)):
            try:
                img = Image.open(filename)
                cond = img.verify()
                return [filename, ]

            except IOError:
                #print "err"
                return False
        else: return False

    def drawlocaltile(self, frame, dc):
        """
        metodo che disegna un tile, può essere chiamato anche appena un tile
        viene scaricato, quindi bisogna controllare che il livello di zoom sia
        conforme
        """
        x, y, _ = self.tile
        zoom = frame.zoom
        id = self.id
        dc.RemoveId(id) 
        dc.ClearId(id)
        dc.SetId(id)
        img = self.loadtile()
        """dc.SetBrush(wx.GREY_BRUSH)
        dc.DrawRectangle(x*256,y*256,256,256)
        dc.DrawText(str(x)+","+str(y), x*256,y*256)"""
        if(img != False):
            self.image = wx.Image(img[0], wx.BITMAP_TYPE_ANY).ConvertToBitmap()
            
            a = dc.DrawBitmap(self.image, x*256, y*256, False)
            dc.SetIdBounds(id, wx.Rect(x*256, y*256, 256, 256))
            frame.objids.append(id)
            return True
        else:
            return False
            
      
class MyMercator(globalmaptiles.GlobalMercator):
    """
    Estendo  la classe GlobalMercator, creando i due metodi che userò nell'applicazione
    """
    
    def __init__(object):
        globalmaptiles.GlobalMercator.__init__(object)

    def pixels_to_lat_lon(self, x, y, zoom):
        """
        converte le coordinate da pixel a (lat, lon) per un certo zoom
        """
        mx, my = mercator.PixelsToMeters(x, y, zoom)
        lat, lon = mercator.MetersToLatLon(mx, my ) 
        #lat corretto
        return -lat, lon
        
    def lat_lon_to_pixels(self, lat, lon, zoom):
        """
        converte le coordinate da (lat, lon) a pixel per un certo zoom
        """
        mx, my = mercator.LatLonToMeters(lat, lon)
        x, y = mercator.MetersToPixels(mx, my, zoom)
        #correzione coordinata y (globalmaptiles ha l'origine sull'orizzonte, \
        #python in alto a sinistra)
        y = ((2**zoom)*256)-y
        return x, y
        
mercator = MyMercator()


class Marker:
    img = wx.Image("images/marker.png", wx.BITMAP_TYPE_ANY)
    
    def __init__(self, lat, lon, name = "", description = ""):
        self.lat = float(lat)
        self.lon = float(lon)
        self.name = name
        self.description = description
        self.id = wx.NewId()
    
    def __str__(self):
        return str(self.lon)+","+str(self.lat)+",0"
    
    def getpixels(self,zoom):
        x,y = mercator.lat_lon_to_pixels(self.lat,self.lon,zoom)
        
        return x,y
    
    def draw(self, frame, dc):
        id = self.id
        dc.RemoveId(id) 
        dc.ClearId(id)
        dc.SetId(id)
        zoom = frame.zoom
        x, y = self.getpixels(zoom)
        
        # sposto il marker (largo 20 e alto 34 pixel) a sinistra di 10 e 
        # in alto di 34
        
        x -= 10
        y -= 34
        dc.SetIdBounds(id, wx.Rect(x, y, 20, 34))
        # Crea il DC e lo prepara per il disegno.
        #frame.dc.BeginDrawing()
        frame.marker_img = self.img.ConvertToBitmap()
        # Disegna un'immagine senza la maschera trasparente.
        img = dc.DrawBitmap(frame.marker_img, int(x), int(y), False)
        dc.SetBrush(wx.WHITE_BRUSH)
        dc.DrawText(self.name, x+20, y)
        dc.SetBrush(wx.BLACK_BRUSH)
        dc.DrawText(self.name, x+21, y+1)

        # Finisce le operazioni di disegno.
        #frame.dc.EndDrawing()
        frame.objids.append(id)
        
        
class LineString:
    """
    Percorso a linee spezzate
    """
    def __init__(self, name = "", description = "", path = ""):
        self.name = name
        self.description = description
        self.path = path
        self.id = wx.NewId()
    
    def __str__(self):
        return str(self.path)
        
    def draw(self, frame, dc):
        """
        disegna la linestring
        """
        id = self.id
        dc.RemoveId(id) 
        dc.ClearId(id)
        dc.SetId(id)
        coords = []
        lat,lon = self.path[0]
        minx, miny = mercator.lat_lon_to_pixels(float(lat), float(lon), frame.zoom)
        maxx, maxy = minx, miny
        for p in self.path:
            lat, lon = p
            p_pixel = mercator.lat_lon_to_pixels(lat, lon, frame.zoom)
            coords.append(p_pixel)
            x, y = p_pixel
            if minx > x:
                minx = x
            if miny > y:
                miny = y
            if maxx < x:
                maxx = x
            if  maxy < y:
                maxy = y
                
        #print "quadrato",minx,miny,maxx,maxy
        dc.SetIdBounds(self.id, wx.Rect(minx, miny, maxx, maxy))
        dc.SetBrush(wx.GREY_BRUSH)
        #dc.DrawRectangle(min,min,max,max)
        dc.SetBrush(wx.BLACK_BRUSH)
        dc.DrawLines(coords, xoffset = 0, yoffset = 0)
        #print "disegnato"
    
        
        
# This creates a new Event class and a EVT binder function
(DownloadImageEvent, EVT_DOWNLOAD_IMAGE) = wx.lib.newevent.NewEvent()


class DownloadThread:
    
    def __init__(self,frame):
        self.frame = frame
        
    def Start(self):
        #self.keepGoing = self.running = True
        thread.start_new_thread(self.Run, ())

    def Stop(self):
        self.keepGoing = False

    def IsRunning(self):
        return self.running
        



    def downloadtile(self, tile):
        #if(x>=0 & y>=0 & zoom>=0):
        x,y,zoom=map(str,tile.tile)
        param="&x="+x+"&y="+y+"&z="+zoom       

        url=baseurlmap[MAP_TYPE]+param
        filename = DIR_CACHE+"/"+x+"-"+y+"-"+zoom+".png"
        #if (os.path.exists(filename)==False):
        #print url
        try:
            url = urllib.urlretrieve(url, filename)
            return url
        except IOError:
            #offline
            pass


    def Run(self):
        #for tile in tiles:
        while True:
            #print self.name+" vivo"
            tile = tile_to_download.get()
            #print self.name+" preso "+str(tile.tile)
            self.img = self.downloadtile(tile)
            #print self.name+" scarico "+str(tile.tile)
            if(self.img!=False):
                evt = DownloadImageEvent(downloaded_tile=tile)
                wx.PostEvent(self.frame, evt)
		#print self.name+" "+str(tile.tile)+" scaricato"
            #print " "+self.name+" morto"
            tile_to_download.task_done()
           
            #self.running = False


class PyMapFrame(wx.Frame):
    
    def __init__(self):
        wx.Frame.__init__(self, None, -1, APP_NAME,pos=(0, 0), size=wx.DisplaySize())
        self.sw = wx.ScrolledWindow(self,style = wx.SUNKEN_BORDER)
        #self.sw.lines = []
        self.zoom = 0
        self.canvasSize = 256
        
        self.mode = "select"
        self.dragid=-1
        #self.sw.curLine = []
        #self.sw.drawing = False

       
        wx.EVT_PAINT(self.sw, self.OnPaint)
        #self.sw.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenuMarker)
        self.sw.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        self.sw.Bind(wx.EVT_SCROLLWIN_THUMBRELEASE, self.OnScroll)
      


        # Id utilizzato dallo slider
        # inseriti nella toolbar.
        ID_SLIDER = wx.NewId()
        tb = self.CreateToolBar(wx.TB_HORIZONTAL|wx.NO_BORDER|wx.TB_FLAT)
        
        self.slider = wx.Slider(tb, wx.ID_ANY,size=[300,50],    style=wx.SL_HORIZONTAL|wx.SL_AUTOTICKS|wx.SL_LABELS|wx.SL_BOTH) 
        
        self.slider.SetTickFreq(1)  
        self.slider.SetRange(0,22)  
        self.slider.SetValue(0)
        self.slider.Bind(wx.EVT_SCROLL_CHANGED, self.OnSlide, self.slider)
        #self.Bind(wx.EVT_SCROLL_CHANGED, self.DoDrawingBtn, self.sw)
        tb.AddControl(self.slider)
        
        new_bmp =  wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR, (30,30))
        #tb.AddLabelTool(10, "New", new_bmp, shortHelp="New", longHelp="Long help for 'New'")
        self.Bind(wx.EVT_TOOL, self.ViewMarker, id=10)
      
        


        # Create the menubar
        menuBar = wx.MenuBar()
        # and a menu 
        filemenu = wx.Menu()
        insertmenu=wx.Menu()
        # add an item to the menu, using \tKeyName automatically
        # creates an accelerator, the third param is some help text
        # that will show up in the statusbar
        ID_NEW = wx.NewId()
        ID_SAVE = wx.NewId()
        ID_ADD = wx.NewId()
        ID_ADD_PATH = wx.NewId()
        ID_EXIT = wx.NewId()
        idimport = wx.NewId()
        
        filemenu.Append(wx.ID_NEW)
        filemenu.Append(wx.ID_OPEN)
        filemenu.Append(idimport, "Import\tAlt-I", "Import")
        filemenu.Append(wx.ID_SAVE)
        insertmenu.Append(wx.ID_ADD,"New Point","New Point")
        insertmenu.Append(ID_ADD_PATH,"New Path","New Path")
        filemenu.Append(wx.ID_EXIT)

        # bind the menu event to an event handler
        #self.Bind(wx.EVT_MENU, self.OnOpen, id=wx.id_import)
        self.Bind(wx.EVT_MENU, self.OnNew, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self.OnOpen, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnImport, id=idimport)
        self.Bind(wx.EVT_MENU, self.OnSave, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.OnNuovopunto, id=wx.ID_ADD)
        self.Bind(wx.EVT_MENU, self.OnNewPath, id=ID_ADD_PATH)
        self.Bind(wx.EVT_MENU, self.OnEsci, id=wx.ID_EXIT)
        
        self.Bind(EVT_DOWNLOAD_IMAGE, self.OnDownload)

        # and put the menu on the menubar
        menuBar.Append(filemenu, "&File")
        menuBar.Append(insertmenu, "&Insert")
        self.SetMenuBar(menuBar)
        
        #array in cui vengono salvati tiles, markers e percorsi
        self.tiles = []
        self.layers = []
        self.markers = []
        self.LineStrings = []
        
        sizeX, sizeY = self.sw.GetSize()
        #self.sw.Scroll(sizeX/2, sizeY/2)
        self.buffer = wx.EmptyBitmap(sizeX*10,sizeY*10)
        
        self.pdc = wx.PseudoDC()
        self.DoDrawing(self.pdc)

        self.CreateStatusBar()
        
        #creo e faccio partire il thread che scarica le tile non presenti
        for i in range(DOWNLOAD_THREAD_NUM):
            DT = DownloadThread(self)
            DT.name = str(i)
            DT.Start()
        

        

        
        
        
        #self.buffer = wx.EmptyBitmap(self.canvasSize,self.canvasSize)
        #self.dc = wx.BufferedDC(None, self.buffer)
        #self.dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        #self.dc.Clear()
        #self.DoDrawing()
        
    """def getTiles(self,zoom,event):
        #print "thread"+str(zoom)
        for x in range(0,2**zoom):
            for y in range(0,2**zoom):
                if(x<5 and y<4):
                    img=downloader.downloadtile(x,y,zoom)
                    #print img
        
        wx.InitAllImageHandlers()
        
        # Carica "mappa.png" in memoria.
        #png = wx.Image(imageFile, wx.BITMAP_TYPE_ANY).ConvertToBitmap()
        #self.png = wx.Image("mappa.png", wx.BITMAP_TYPE_ANY).ConvertToBitmap()
    """
    def ConvertEventCoords(self, event):
        xView, yView = self.sw.GetViewStart()
        xDelta, yDelta = self.sw.GetScrollPixelsPerUnit()
        return (event.GetX() + (xView * xDelta),
            event.GetY() + (yView * yDelta))
            
    def OffsetRect(self, r):
        xView, yView = self.sw.GetViewStart()
        xDelta, yDelta = self.sw.GetScrollPixelsPerUnit()
        r.OffsetXY(-(xView*xDelta),-(yView*yDelta))
    
    def LookAt(self, lat, lon, zoom):
        #visualizza il punto alle coordinate (lat,lon), allo zoom attuale
        x, y = mercator.lat_lon_to_pixels(lat, lon, zoom)
        xFrame, yFrame = self.sw.GetSize()
        #print "sw",x,y
        x = x-xFrame/2
        y = y-yFrame/2
        self.sw.Scroll(x/20, y/20)
        self.DoDrawing(self.pdc)

    
    
        
    
    def ViewMarker(self, event):
        
        lat, lon = self.markers[0].lat,self.markers[0].lon
        self.LookAt(lat, lon, self.zoom)
    
    
    def OnPaint(self, event):
        #print "("+str(minX)+","+str(minY)+") ("+str(maxX)+","+str(maxY)+")"
        #print self.sw.GetViewStart()
        #print self.sw.CalcUnscrolledPosition((0,0))
        #print self.sw.GetSize()
        #print self.sw.GetScrollPixelsPerUnit() 
        
        #dc = wx.BufferedPaintDC(self.sw, self.buffer, wx.BUFFER_VIRTUAL_AREA)
        
        #if(minX > 0 and minY > 0):
        #dc1=wx.PaintDC(self.sw)
        #self.sw.DoPrepareDC(dc1)
        #self.DoDrawing(dc1)
        #self.DoDrawing(self.pdc)
        dc = wx.BufferedPaintDC(self.sw)
        self.sw.PrepareDC(dc)
        dc.Clear()
        xv, yv = self.sw.GetViewStart()
        dx, dy = self.sw.GetScrollPixelsPerUnit()
        x, y  = (xv * dx, yv * dy)

        #print "xy",x,y
        rgn = self.sw.GetUpdateRegion()
        #print "region",rgn
        rgn.Offset(x, y)
        sx, sy=self.sw.GetSize()
        r=(x, y, sx, sy)
        r=rgn.GetBox()
        #self.DoDrawing(self.pdc)
        self.pdc.DrawToDCClipped(dc, r)
        self.pdc.DrawToDC(dc)
        #print "linee",self.LineStrings
        """for l in self.LineStrings:
            print l.path"""
        
    
    
    def OnDownload(self, evt):
        """
        appena viene scaricata una tile, viene rappresentata (se il livello di zoom è corretto)
        """
        if (evt.downloaded_tile!=None and (evt.downloaded_tile.tile[2]==self.zoom)):
            newTile = evt.downloaded_tile
            #print "onDownload "+str(newTile.tile)
            dc = self.pdc
            dc.BeginDrawing()
            newTile.drawlocaltile(self, dc)
            for m in self.markers:
                m.draw(self, dc)
            for p in self.LineStrings:
                p.draw(self, dc)
                #points.append(m.getpixels(zoom))
            #dc.DrawLines(points, xoffset=0, yoffset=0)
            dc.EndDrawing()
            self.OnPaint(evt)
            



            
    def OnScroll(self, evt):
        """if(evt.GetPosition()==wx.HORIZONTAL):
            print "orizzontale"
        if(evt.GetPosition()==wx.VERTICAL):
            print "verticale"""
        self.DoDrawing(self.pdc)
	self.OnPaint(evt)

    
    def put_tile_in_queue(self,tile):
        """se il tile appartiene al livello di zoom attuale, viene inserito nella coda per essere scaricato dal downloadthread"""
        if(tile.tile[2]==self.zoom):
            tile_to_download.put(tile)
            #print "messo",tile.tile

    
    #disegna la mappa e gli oggetti all'interno dell'area attualmente visibile
    def DoDrawing(self, dc):
        self.objids = []
        self.boundsdict = {}
        
        zoom = self.zoom
        

        # Crea il DC e lo prepara per il disegno.
        #self.dc = wx.PaintDC(self.sw)
        dc.BeginDrawing()
        
        
        # dalla dimensione della finestra e posizione  attuale, calcolo quali
        # tile devono essere disegnate
        xv, yv = self.sw.GetViewStart()
        dx, dy = self.sw.GetScrollPixelsPerUnit()
        minX, minY  = (xv * dx, yv * dy)
        
        maxX, maxY = self.sw.GetSize()
        minX = int(math.floor(minX/256)) #floor: approssimazione per difetto
        minY = int(math.floor(minY/256))
        
        maxX = int(math.ceil(minX+maxX/256+2))#ceil: approssimazione per eccesso
        maxY = int(math.ceil(minY+maxY/256+2))
        #dc.Clear()
        #dc.BeginDrawing()
        
        if(maxX>2**zoom):
            maxX = 2**zoom
        if(maxY>2**zoom):
            maxY = 2**zoom
        
        found = False
        for x in range(minX, maxX):
            for y in range(minY, maxY):
                
                #controllo se il tile e' gia' stato disegnato
                for t in self.tiles:
                    if t.tile==(x, y, zoom):
                        found = True
                
                #se non e' gia' stato disegnato, creo l'oggetto
                if not found:
                    newTile = Tile(x, y, zoom)
                    #print "creato",newTile.tile
                    
                    #se riesco a disegnarlo, lo metto nel vettore
                    if newTile.drawlocaltile(self, dc):
                        self.tiles.append(newTile)
                    else:
                        # aggiungo alla coda il tile da scaricare aspettando \
                        # QUEUE_WAIT secondi
                        if(not tile_to_download.full()):
                            t = Timer(QUEUE_WAIT, self.put_tile_in_queue, args=[newTile, ])
                            t.start() 
                            
                            #tile_to_download.put(newTile)
                            #print "messo",newTile.tile
                #print x,y
            found = False
        
        #disegno i markers
        for m in self.markers:
            m.draw(self, dc)
            
        #disegno i path
        for p in self.LineStrings:
            p.draw(self, dc)


        # Finisce le operazioni di disegno.
        dc.EndDrawing()
        print "tile in memoria: "+str(len(self.tiles))
        

    

    def Zoom(self, lat, lon, zoom, event=None):
        #svuoto la coda tile_to_download
        """for i in range(tile_to_download.qsize()):
            if tile_to_download.qsize()>0:
                tile_to_download.get_nowait()"""
        #print "dim", tile_to_download.qsize()
        #elimino tutti gli id
        self.pdc.RemoveAll()
        """for t in self.tiles:
            self.pdc.RemoveId(t.id) 
            self.pdc.ClearId(t.id)
        for m in self.markers:
            self.pdc.RemoveId(m.id)
            self.pdc.ClearId(m.id)"""
        self.tiles = []
        if zoom <= 3:
            self.pdc.Clear()
        self.zoom = zoom
        #impostazioni barre di scorrimento
        self.canvasSize = (2**zoom)*256
        self.sw.SetVirtualSize((self.canvasSize, self.canvasSize))
        self.sw.SetScrollRate(20,20)
        #self.DoDrawing(self.pdc)
        self.LookAt(lat, lon, self.zoom)
        #self.DoDrawing(self.pdc)
        self.OnPaint(event)

        
        
    def OnSlide(self, event):
        """
        metodo chiamato quando si muove lo slider: cambia il livello dello
        zoom centrando mantenendo lo stesso centro dell'immagine
        """
        self.tiles = []
        xFrame,yFrame = self.sw.GetSize()
        xCenter = xFrame/2
        yCenter = yFrame/2
        xView, yView = self.sw.GetViewStart()
        xDelta, yDelta = self.sw.GetScrollPixelsPerUnit()
        x,y=(xCenter + (xView * xDelta),yCenter + (yView * yDelta))
        print "x,y", x, y
        lat,lon=mercator.pixels_to_lat_lon(x, y, self.zoom)
        print "lat,lon", lat, lon
        #self.slider.SetValue(self.zoom)
        #self.DoDrawing(self.pdc)
        self.zoom = self.slider.GetValue()
        #self.slider.SetValue(self.zoom)
        self.Zoom(lat, lon, self.zoom, event)
        

        
   
        
    def OnNuovopunto(self, event):
        self.NewPointDialog(coords="38.132329,15.158815")

        
    
    """def NewPointDialog(self,coords):
        dlg = wx.TextEntryDialog(self, 'Inserisci le coordinate','Nuovo punto', 'Python')
        
        dlg.SetValue(coords)
        if dlg.ShowModal() == wx.ID_OK:
            coordinate=dlg.GetValue()
            lat,lon=coordinate.split(",")
            newMarker=Marker(lat,lon)
            self.markers.append(newMarker)
        dlg.Destroy()
        self.DoDrawing(self.pdc)"""
    
    def NewPointDialog(self, coords):
        dialog = marker_dialog.MarkerDialog(None, -1, "")
        dialog.coordinates.SetValue(coords)
        dialog.SetTitle("New Point")
        val = dialog.ShowModal()
        print val
        if val == wx.ID_OK:
            coordinate = dialog.coordinates.GetValue()
            lat, lon = coordinate.split(",")
            name = dialog.name.GetValue()
            description = dialog.description.GetValue()
            newMarker = Marker(lat, lon, name, description)
            self.markers.append(newMarker)
            newMarker.draw(self, self.pdc)
        dialog.Destroy()
       
        
    def OnNewPath(self, event):
        self.tempPath = []
        self.mode = "path"
        self.NewPathDialog(event)
        
    def NewPathDialog(self, event):
        self.PathDialog = path_dialog.PathDialog(None, -1, "")
        self.PathDialog.SetTitle("New Path")
        self.PathDialog.Bind(wx.EVT_BUTTON, self.OnNewPathOk, 
                id = self.PathDialog.ID_NEWPATH)
        val = self.PathDialog.Show()
    
    
    def OnNewPathOk(self, event):
        name = self.PathDialog.name.GetValue()
        description = self.PathDialog.description.GetValue()
        
        #creo il nuovo oggetto linestring e lo aggiungo al vettore dei 
        #       linestring
        newLineString = LineString(name, description, self.tempPath)
        self.LineStrings.append(newLineString)
        
        #ripristino la modalita' select e chiudo la finestra newpath
        self.mode="select"
        self.PathDialog.Destroy()
        
    
    
    
    def load_kml(self,namefile):
        #carica i markers da file kml e restituisce la lista di markers
        markers=[]
        import xml.dom.minidom
        from xml.dom.minidom import Node
         
        doc = xml.dom.minidom.parse(namefile)
        p_name = ""
        p_description = ""
        for node in doc.getElementsByTagName("Placemark"):
            name = node.getElementsByTagName("name")
            
            for node1 in name:
                for n in node1.childNodes:
                    p_name = n.data.encode('utf8')
                    print p_name
    
            description = node.getElementsByTagName("description")
            for desc in description:
                for des in desc.childNodes:
                    p_description=(des.data).encode('utf8')
                    print p_description
            
            point = node.getElementsByTagName("Point")
            if len(point)>0:
                for node2 in point:
                    coordinates = node2.getElementsByTagName("coordinates")
                    for node3 in coordinates:
                        for node4 in node3.childNodes:
                            p_coordinates = node4.data.encode('utf8')
                            #print p_coordinates
                            lon, lat, hi = p_coordinates.split(",")
                            newMarker = Marker(lat, lon, p_name, p_description)
                            self.markers.append(newMarker)
                            newMarker.draw(self, self. pdc)
            
            linestring = node.getElementsByTagName("LineString")
            if len(linestring)>0:
                for node2 in linestring:
                    newpath = []
                    coordinates = node2.getElementsByTagName("coordinates")
                    for node3 in coordinates:
                        for node4 in node3.childNodes:
                            p_coordinates = node4.data.encode('utf8')
                            co = p_coordinates.split("\n")
                            #print "righe",co
                            for p in co:
                                if(p.strip()!=""):
                                    #print "riga",p
                                    lon, lat, hi=p.split(",")
                                    newpath.append((float(lat), float(lon)))
                                    #print newpath
                    newLineString = LineString(path = newpath)
                    self.LineStrings.append(newLineString)

        return markers
    
    
    def OnContextMenuMarker(self, marker):

        if not hasattr(self, "popupID1"):
            self.popupID1 = wx.NewId()
            self.popupID2 = wx.NewId()
        
        
        def UpdateMarkerDialog(self, marker = marker):
            dialog = marker_dialog.MarkerDialog(None, -1, "")
            dialog.coordinates.SetValue(str(marker.lat)+","+str(marker.lon))
            dialog.name.SetValue(marker.name)
            dialog.description.SetValue(marker.description)
            dialog.SetTitle("Edit Marker properties")
            val = dialog.ShowModal()
            if val == wx.ID_OK:
                coordinate=dialog.coordinates.GetValue()
                lat,lon = coordinate.split(",")
                marker.lat = float(lat)
                marker.lon = float(lon)
                marker.name = dialog.name.GetValue()
                marker.description = dialog.description.GetValue()
                #newMarker=Marker(lat,lon,name,description)
                #self.markers.append(newMarker)
                #marker.draw(self,self.pdc)
            dialog.Destroy()
            
            

        
        def Ondelete(event,marker = marker):            
            id = marker.id
            self.pdc.RemoveId(id) 
            self.pdc.ClearId(id)
            self.markers.remove(marker)
            menu.Destroy
            self.OnPaint(event)

        #self.Bind(wx.EVT_MENU, self.Ondelete, id=self.popupID1)
        self.Bind(wx.EVT_MENU, UpdateMarkerDialog, id = self.popupID1)
        self.Bind(wx.EVT_MENU, Ondelete, id = self.popupID2)
        # make a menu
        menu = wx.Menu()
        # Show how to put an icon in the menu
        # add some other items
        menu.Append(self.popupID1, "Properties "+marker.name)
        menu.Append(self.popupID2, "Delete")
        # Popup the menu.  If an item is selected then its handler
        # will be called before PopupMenu returns.
        self.PopupMenu(menu)
        menu.Destroy()
        
        
        
    def OnContextMenuLineString(self, LineString):

        if not hasattr(self, "popupID1"):
            self.popupID1 = wx.NewId()
            self.popupID2 = wx.NewId()
        
        
        def UpdateLineStringDialog(self, linestring = LineString):
            dialog = path_dialog.PathDialog(None, -1, "")
            #dialog.coordinates.SetValue(str(marker.lat)+","+str(marker.lon))
            dialog.name.SetValue(linestring.name)
            dialog.description.SetValue(linestring.description)
            dialog.SetTitle("Edit LineString properties")
            val = dialog.ShowModal()
            print val
            if val == dialog.ID_NEWPATH:
                #coordinate=dialog.coordinates.GetValue()
                #lat,lon = coordinate.split(",")
                linestring.name = dialog.name.GetValue()
                linestring.description = dialog.description.GetValue()
                #newMarker=Marker(lat,lon,name,description)
                #self.markers.append(newMarker)
                #marker.draw(self,self.pdc)
            dialog.Destroy()

        def Ondelete(event,linestring = LineString):            
            id = linestring.id
            self.pdc.RemoveId(id) 
            self.pdc.ClearId(id)
            self.LineStrings.remove(linestring)
            menu.Destroy
            self.OnPaint(event)

        #self.Bind(wx.EVT_MENU, self.Ondelete, id=self.popupID1)
        self.Bind(wx.EVT_MENU, UpdateLineStringDialog, id = self.popupID1)
        self.Bind(wx.EVT_MENU, Ondelete, id = self.popupID2)
        # make a menu
        menu = wx.Menu()
        # Show how to put an icon in the menu
        # add some other items
        menu.Append(self.popupID1, "Properties path "+LineString.name)
        menu.Append(self.popupID2, "Delete path")
        # Popup the menu.  If an item is selected then its handler
        # will be called before PopupMenu returns.
        self.PopupMenu(menu)
        menu.Destroy()
        
        
        
    def OnContextMenuMap(self, coord):


        if not hasattr(self, "popupIDnew"):
            self.popupIDnew = wx.NewId()

        def OnNewPoint(event, coord = coord):            
            self.NewPointDialog(coord)
            menu.Destroy
            self.OnPaint(event)

        self.Bind(wx.EVT_MENU, OnNewPoint, id=self.popupIDnew)
        # make a menu
        menu = wx.Menu()
        # Show how to put an icon in the menu
        # add some other items
        menu.Append(self.popupIDnew, "New Point")
        # Popup the menu.  If an item is selected then its handler
        # will be called before PopupMenu returns.
        self.PopupMenu(menu)
        menu.Destroy()
    
    
    
    
    def OnMouse(self,event):
        x,y = self.ConvertEventCoords(event)
        lat,lon = mercator.pixels_to_lat_lon(x, y, self.zoom)
        self.SetStatusText(str(lat)+","+str(lon))
        
        if event.LeftDown():
            #se sono in modalità "disegna percorso":
            if self.mode=="path":
                dc = wx.PaintDC(self.sw)
                #newmarker=Marker(lat,lon)
                #self.markers.append(newmarker)
                #newmarker.draw(self,dc)
                point = (lat, lon)
                self.tempPath.append(point)
                coords = []
                ls = LineString(path = self.tempPath)
                ls.draw(self, self.pdc)
                #print self.tempPath
            else:
                
                #self.slider.SetValue(self.zoom)
                #self.zoom+=1
                #self.DoDrawing(self.pdc)
                #self.slider.SetValue(self.zoom)
                
                #print "x,y",x,y
                #print "lat,lon",lat,lon
                self.LookAt(lat, lon, self.zoom)
                #self.Zoom(self.zoom,lat,lon)
                l = self.pdc.FindObjects(x, y, 5)

                
                self.DoDrawing(self.pdc)
            self.OnPaint(event)


        elif event.RightDown():
            x, y = self.ConvertEventCoords(event)
            l = self.pdc.FindObjects(x, y, 1)#lista di id oggetti disegnati
            print l
            found=False
            for id in l:
                for m in self.markers:
                    if m.id == id:
                        """self.pdc.RemoveId(id) 
                        self.pdc.ClearId(id)
                        self.lastpos = (event.GetX(),event.GetY())"""
                        self.OnContextMenuMarker(m)
                        found=True
                for line in self.LineStrings:
                    if line.id == id:
                        self.OnContextMenuLineString(line)
                        found=True
                if found:
                    break
            if not found:
                lat,lon=mercator.pixels_to_lat_lon(x,y,self.zoom)
                #new point
                coord=str(lat)+","+str(lon)
                self.OnContextMenuMap(coord)

        elif event.GetWheelRotation() > 0:
            x, y = self.ConvertEventCoords(event)
            lat, lon = mercator.pixels_to_lat_lon(x, y, self.zoom)
            #self.slider.SetValue(self.zoom)
            if (self.zoom != 22):
                self.zoom += 1
                #self.DoDrawing(self.pdc)
                self.slider.SetValue(self.zoom)
                self.Zoom(lat,lon,self.zoom,event)
                
        elif event.GetWheelRotation() < 0:
            x, y = self.ConvertEventCoords(event)
            lat, lon = mercator.pixels_to_lat_lon(x, y, self.zoom)
            #self.slider.SetValue(self.zoom)
            if (self.zoom != 0):
                self.zoom -= 1
                #self.DoDrawing(self.pdc)
                self.slider.SetValue(self.zoom)
                self.Zoom(lat, lon, self.zoom, event)

    
    def OnImport(self,event,action="import"):
        wildcard = "KML file (*.kml)|*.kml|"        \
           "All files (*.*)|*.*"
        dlg = wx.FileDialog(
        self, message = "Choose a file",
        #defaultDir = os.getcwd(), 
        defaultFile = "",
        wildcard = wildcard,
        style = wx.OPEN | wx.MULTIPLE | wx.CHANGE_DIR
        )
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            if action == "new":
                self.OnNew(event)
            
            paths = dlg.GetPaths()
            for pat in paths:
                self.load_kml(pat)
        dlg.Destroy()
        self.DoDrawing(self.pdc)
        self.OnPaint(event)

    
    def OnOpen(self,event):
        #self.OnNew(event)
        self.OnImport(event,action = "new")
        #self.DoDrawing(self.pdc)
    
    def OnNew(self, event):
        for m in self.markers:
            self.pdc.RemoveId(m.id) 
            self.pdc.ClearId(m.id)
        self.markers = []
        self.OnPaint(event)

        
        for l in self.LineStrings:
            self.pdc.RemoveId(l.id) 
            self.pdc.ClearId(l.id)
        self.LineStrings = []
        self.DoDrawing(self.pdc)
        








    def create_kml(self):
        # Create the minidom document
        doc = Document()

        # Create the <kml> base element
        kml = doc.createElement("kml")
        kml.setAttribute("xmlns", "http://www.opengis.net/kml/2.2")
        doc.appendChild(kml)
        document = doc.createElement("Document")
        kml.appendChild(document)

        for marker in self.markers:
            # Create the main <Placemark> element
            placemark = doc.createElement("Placemark")
            document.appendChild(placemark)

            # Append <name> element
            name = doc.createElement("name")
            placemark.appendChild(name)
            name.appendChild(doc.createTextNode(marker.name))

            # Append <description> element
            description = doc.createElement("description")
            placemark.appendChild(description)
            description.appendChild(doc.createTextNode(marker.description))

            # Append <Point> element
            point = doc.createElement("Point")
            placemark.appendChild(point)

            # Append <Coordinates> element
            coordinates = doc.createElement("coordinates")
            point.appendChild(coordinates)
            coordinates.appendChild(doc.createTextNode(str(marker)))
        
        for l in self.LineStrings:
            print "percorso"
            # Create the main <Placemark> element
            placemark = doc.createElement("Placemark")
            document.appendChild(placemark)
            
            # Append <name> element
            name = doc.createElement("name")
            placemark.appendChild(name)
            name.appendChild(doc.createTextNode(l.name))
            
            # Append <description> element
            description = doc.createElement("description")
            placemark.appendChild(description)
            description.appendChild(doc.createTextNode(l.description))
            
            # Append <LineString> element
            linestring = doc.createElement("LineString")
            placemark.appendChild(linestring)
            
            # Append <Tessellate> element
            tessellate = doc.createElement("tessellate")
            linestring.appendChild(tessellate)
            tessellate.appendChild(doc.createTextNode(str(1)))

            
            # Append <Coordinates> element
            coordinates = doc.createElement("coordinates")
            for p in l.path:
                lat,lon=p
                linestring.appendChild(coordinates)
                coordinates.appendChild(doc.createTextNode(str(lon)+","+str(lat)+",0"+"\n"))
        return doc.toxml()
    





        
    def OnSave(self, event):
        wildcard = "KML file (*.kml)|*.kml|"        \
           "All files (*.*)|*.*"
        dlg = wx.FileDialog(self, message = "Save file as ...", 
            defaultDir=os.getcwd(), defaultFile = "", wildcard = wildcard, 
            style = wx.SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            fp = file(path, 'w') 
            data=self.create_kml()
            fp.write(data)
            fp.close()
        dlg.Destroy()
        
        
    def OnEsci(self, event):
        # Distrugge il frame.
        self.Close(1)
        
        
class PyMap(wx.App):
    def OnInit(self):
        #create cache folder if it does not exist
        d = os.path.dirname(DIR_CACHE)
        if not os.path.exists(d):
            os.makedirs(d)
        frame = PyMapFrame()
        frame.Show(1)
        self.SetTopWindow(frame)
        return 1

app = PyMap()
app.MainLoop()
