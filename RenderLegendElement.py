#!/usr/bin/python
# This script is (really) a work in progress
"""
Input:
 _ mapnik stylesheet
 _ elementType: point, line, square, rectangle, pointtext, linetext,
   lineshield, squaretext, rectangletext, squarepoint and smallline
 _ tagList in python style ["[key]='value'", "[key]='value'"]
 _ style, to select the appropriate layer
 _ zoom
 _ imageWidth, image heigth is calculated, and anyway the output is
   cropped to its smallest extent
 _ image filename
 Intermediate computation:
  _ element.osm is a temporary osm-type xml file of the element to be
    rendered, centered on (lat,lon) (0,0)
  _ mapfile.xml is a temporary mapnik style sheet, copy of the
    previous with the following modifications:
     * bgcolor
     * removed world, coastpoly, etc ... layer
     * datasource set to osm, element.osm
 Output:
  _ png image of width =< 'width'
  
 The mapnik osm datasource plugin does not features (yet ?) the 
osm2pgsql handling of polygons.
Thus area features (ie rectangle and squares) are affected with a tag
[is_area]='yes' and all rules from the style sheet not featuring a 
PolygonSymbolizer are modified with "and not ([is_area]='yes')" to avoid
rendering artifacts.
Central points and 'name' should be precised with to rectanglepoint 
and rectangletext elements, resp. squarepoint and squaretext.
"""
__license__ = "GPL"
__author__ = "Yves Cainaud"

import mapnik
from mapnik import Osm, Map, load_map, save_map # allow us to change the mapFile datasource

import re
import StringIO
import tempfile
import os
import pdb
import xml.dom.minidom as m
from xml.dom.minidom import getDOMImplementation
import Image
import ImageChops
import ImageFile

# lat-lon geometry elements
# faclat is the 'width' factor defining a common width for elements
# faclon is the 'height' factor
# rectangles have ratio faclat/faclon
faclat=0.003
faclon=0.006

# cemetery : look for "INT-generic"
# issue with buildings point-symbolizer

def create_legend_stylesheet(inputstylesheet):#,outputstylesheet):
    """create legend-style.xml, a temporary mapnik style sheet, copy of
    the input stylesheet with the following modifications:
    * bgcolor
    * removed world, coastpoly, etc ... layers
    * postgis datasource query transformed into rule filter with 
      queryToFilter(sql) function
    * <else> filter is replaced by a filter that negates previous ones
    * if no PolygonSymbolizer is found in the rule, and not (area=yes) is
      added to the filter
    """
    
    doc = m.parse(inputstylesheet)
    map = doc.getElementsByTagName("Map")
    layers = doc.getElementsByTagName("Layer")
    
    # create a (style:[query list]) dictionnary with queries found in the\
    # layers' Postgis datasource table.
    # Note: we can have the same style applied to several
    # layers, in that case -> or
    queriesToFilter={}
    for layer in layers:
        for l in layer.getElementsByTagName("StyleName"):
            stylename=l.childNodes[0].nodeValue
            datasource=layer.getElementsByTagName("Datasource")
            for par in datasource[0].getElementsByTagName("Parameter"):
                if par.hasAttribute('name'):
                    if par.getAttribute('name') == "table":
                        query = par.firstChild.nodeValue
                        # little clean up
                        query = query.replace('\n',' ').strip(' ')
                        while query.find('  ') != -1:
                            query = query.replace('  ',' ')
                        if queriesToFilter.has_key(stylename):
                            queriesToFilter[stylename].append(\
                             queryToFilter(query))
                        else:
                            queriesToFilter[stylename]=\
                             [queryToFilter(query)]

    # for each rule filter append the queryfilter extracted from the \
    # layer matching the filename.
    styles = doc.getElementsByTagName("Style")
    for style in styles:
        stylename=style.getAttribute("name")
#       if stylename == "highway-area-casing":
#           pass #map[0].removeChild(style)
        
        allFilterFromStyle=[]
        for r in style.getElementsByTagName("Rule"):
            filter = r.getElementsByTagName("Filter")
            elsefilter=r.getElementsByTagName("ElseFilter")
            
            # If there is a filter section, we take the filter, 
            # and append AND(queryToFilter[0] OR queryToFilter[1]...)
            if len(filter):
                rulefilter = filter[0].firstChild.nodeValue
                
                #For a particular style, we save all the ruleFilters
                # to negate it in the ElseFilter if any
                allFilterFromStyle.append(rulefilter)
                # join all the filter obtained from queryToFilter
                queriesToFilters=''
                if stylename in queriesToFilter.keys():
                    for q in queriesToFilter[stylename]:
                        queriesToFilters += ' or '+ q
                    queriesToFilters = queriesToFilters[4:]
                    
                    filter[0].firstChild.nodeValue = \
                    '('+rulefilter+') and ('+queriesToFilters+')'
            
            # If there is a no filter section, and no ElseFilter
            # we create a <filter> with
            # (queryToFilter[0] OR queryToFilter[1]...)
            elif len(filter) ==0 and len(elsefilter) == 0:
                queriesToFilters=''
                if stylename in queriesToFilter.keys():
                    for q in queriesToFilter[stylename]:
                        queriesToFilters += ' or '+ q
                    queriesToFilters = queriesToFilters[4:]
                    f=doc.createElement("Filter")
                    r.appendChild(f)
                    filtertext = doc.createTextNode(\
                     queriesToFilters)
                    f.appendChild(filtertext)
            
            # replace ElseFilter with a filter that negate the 
            # previous filters in the style
            # otherwise it would render on top of them
            if len(elsefilter): 
                r.removeChild(elsefilter[0])
                allFilters=''
                for filterFromStyle in allFilterFromStyle:
                    allFilters = allFilters +' and not '+ filterFromStyle
                allFilters=allFilters[9:]
                queriesToFilters=''
                if stylename in queriesToFilter.keys():
                    for q in queriesToFilter[stylename]:
                        queriesToFilters += ' or '+ q
                    queriesToFilters = queriesToFilters[4:]
                    f=doc.createElement("Filter")
                    r.appendChild(f)
                    filtertext = doc.createTextNode(\
                     '(' + queriesToFilters+') and not '+ allFilters )
                    f.appendChild(filtertext)
                    
                else:
                    f=doc.createElement("Filter")
                    r.appendChild(f)
                    filtertext = doc.createTextNode(\
                     ' not ('+ allFilters +')')
                    f.appendChild(filtertext)
    
    # Replace the background colors:
    map = doc.getElementsByTagName("Map")
    if map[0].hasAttribute("bgcolor"):
        map[0].setAttribute("bgcolor", "rgb(254,254,254)")
    map = doc.getElementsByTagName("Map")
    
    # Remove world, coast-poly and builtup layers to avoid artifacts from shapefiles:
    nodelist= map[0].childNodes
    l=0
    for node in nodelist:
        l += 1
        if (node._get_localName() == "Layer"):
            if node.hasAttribute("name"):
                if node.getAttribute("name") == "world":
                    map[0].removeChild(map[0].childNodes[l-1])
                if node.getAttribute("name") == "coast-poly":
                    map[0].removeChild(map[0].childNodes[l-1])
                if node.getAttribute("name") == "builtup":
                    map[0].removeChild(map[0].childNodes[l-1])
    
    # filter out polygons from non-polygon symbolizers
    rules = doc.getElementsByTagName("Rule")
    for rule in rules:
        filter = rule.getElementsByTagName("Filter")
        if len(rule.getElementsByTagName("PolygonSymbolizer"))== 0 and \
         len(rule.getElementsByTagName("PolygonPatternSymbolizer"))== 0 \
         and len(filter):
            filter[0].firstChild.nodeValue = '('+\
             filter[0].firstChild.nodeValue +\
             ') and not [is_area]=\'yes\''
             
    return str(doc.toxml())
#
def queryToFilter(sql):
    """ Parses the postgis query found in a stylesheet to transform it 
    into something syntixically equivalent to a rule filter.
    This is not a complete sql parser.
    Really ugly hacks are commented FIXME
    """
    
    query=sql.lower()
    # First, keep only the interesting part of the query
    queryFilter=query.split('where ')[1]
    queryFilter=queryFilter.split('as ')[0]
    queryFilter=queryFilter.strip(' ')
    if queryFilter[-1] == (')'): queryFilter=queryFilter[:-1]
    queryFilter=queryFilter.split('order ')[0]
    
    
    # change tags operators to compatible ones with rule filters syntax
    while (queryFilter.find('is not null')<> -1):
        queryFilter=queryFilter.replace('is not null','<>\'\'')
    while (queryFilter.find('!=')<> -1):
        queryFilter=queryFilter.replace('!=','<>')
    while (queryFilter.find('\"') <> -1):
        queryFilter=queryFilter.replace('\"','')
    
    # remove key if'key is null'
    queryFilter=re.sub('([a-zA-Z:0-9_;]*\sis\snull\sor\s[a-zA-Z:0-9_;]*\s(not\s)*in\s\([^)]*\))|([a-zA-Z:0-9_;]*\sis\snull\sor\s[a-zA-Z:0-9_;]*\s*<>\s*[\'a-zA-Z:0-9_;]*)','',queryFilter)
    queryFilter=re.sub('[a-zA-Z:0-9_;]*\sis\snull\sand','',queryFilter)
    # symplify not in ('no','false','0')
    queryFilter=re.sub(\
    'not\s+in\s*\(\'no\',\'false\',\'0\'\)','=\'yes\'',queryFilter)
    
    # Flattens 'key not in (value1, value2, ...)' to [key]<>'value'
    notins=re.findall(\
    '[a-zA-Z:0-9_;]*\snot\sin\s*\([^)]*\)',queryFilter)
    for n in notins:
        flatten=''
        key=n[:n.find('not in')].strip(' ')
        values=re.findall('\'[^\']*\'',n)
        for value in values:
            flatten+='['+key+']<>'+value + ' or '
        flatten='('+flatten[:-4]+')'
        queryFilter=queryFilter.replace(n,flatten)
    
    # Flattens 'key in (value1, value2, ...)' to [key]='value'
    ins=re.findall('[a-zA-Z:0-9_;]*\sin\s*\([^)]*\)',queryFilter)
    for n in ins:
        flatten=''
        key=n[:n.find('in')].strip(' ')
        values=re.findall('\'[^\']*\'',n)
        for value in values:
            flatten+='['+key+']='+value + ' or '
        flatten='('+flatten[:-4]+')'
        queryFilter=queryFilter.replace(n,flatten)
    
    #handle the turning-circle syntax FIXME
    queryFilter=re.sub('(p\.)|(l\.)','',queryFilter)
    
    #remove extra spaces:
    queryFilter=re.sub('\s<','<',queryFilter)
    queryFilter=re.sub('>\s','>',queryFilter)
    queryFilter=re.sub('\s=','=',queryFilter)
    
    #add [] around keys
    keys=re.findall('[a-zA-Z0-9_:;]+=',queryFilter)
    keys.extend(re.findall('[a-zA-Z0-9_:;]+<',queryFilter))
    keys=list(set(keys)) #remove doublons
    keys.sort()
    keys.reverse()
    for t in keys:
        queryFilter=queryFilter.replace(t,'['+t[:-1]+']'+t[-1])
    
    # identify polygons, they will be tagged [is_area]='yes' and filtered 
    if sql.find('planet_osm_polygon') != -1:
        queryFilter = '( '+queryFilter+' ) and [is_area]=\'yes\''
    
    return queryFilter
#
def getTagKey(lo): #[key]='value' -> key
    key=lo[lo.find("[")+1:lo.find("]")]
    if key:
        return key
    else:
        return 'null'
def getTagValue(lo): #[key]='value' -> value
    if (lo.find("\'")!= -1): value=lo[lo.find("\'")+1:-1]
    else: value=re.findall('[0-9]+',lo)[0]
    if value:
        return value
    else:
        return ''
#
def insertNode(osmDatabase,id,lat,lon):
    # fac=100000 if projection set to mercator
    fac=1
    osmDatabase.write("  <node id=\"" + str(id) +"\" lat=\""+ str(lat*fac) +"\" lon=\""+ str(lon*fac) +"\" visible=\"true\">\n")
    return True
#
def createOsmElement(elementType, tagList, zoom):
    # -> return an .osm  xml file with the element requested
    # a node, a straight, rectangular or square way, ...
    # * rectanglepoint and squarepoint contains a node at the center
    # * -text elements contain the tag [name]='name'
    # * lineshield contains a [ref]='ref' tag, although the elements are
    #    probbaly not long enough to see any ShieldSymbolizer FIXME 
    fosm = StringIO.StringIO()
    fosm.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
    <osm version=\"0.6\" generator=\"legend2osm\">\n\
    <bounds minlat=\"-85\" minlon=\"-180\" maxlat=\"85\" maxlon=\"180\"/>\n")
    # Geometry elements
    #Origin
    lat0 = 0
    lon0 = 0
    #Size of the line and rectangle/square elements
    dlon = faclon * (2**13)/(2**zoom)   #length
    dlat = faclat * (2**13)/(2**zoom)   #height
    
    #space between elements
    if elementType == 'point':
        insertNode(fosm,-10,0,0)
        #pdb.set_trace()
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"point\" v=\"yes\"/>\n")
        fosm.write("  </node>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=(lat0 - dlat/2, lat0 - dlat/2, lat0 + dlat/2, lat0 + dlat/2)
        return strOSm, bbox
    #
    if elementType == 'pointtext':
        insertNode(fosm,-10,0,0)
        #pdb.set_trace()
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"point\" v=\"yes\"/>\n")
        fosm.write( "    <tag k=\"name\" v=\"name\"/>\n")
        fosm.write("  </node>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=(lon0 - dlon/2, lat0 - 2*dlat/2, lon0 + dlon/2, lat0 + 2*dlat/2)
        return strOSm, bbox
    #
    if elementType == 'line':
        insertNode(fosm,-10,0,lon0 - dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,0,lon0 + dlon/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-12\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2), lat0 - dlat/2*1.5, (lon0 + dlon/2), lat0 + dlat/2*1.5)
        return strOSm, bbox
    #
    if elementType == 'smallline':
        insertNode(fosm,-10,0,lon0 - dlon/2*0.6)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,0,lon0 + dlon/2*0.6)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-12\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2), lat0 - dlat/2*1.5, (lon0 + dlon/2), lat0 + dlat/2*1.5)
        return strOSm, bbox
    #
    if elementType == 'linetext':
        insertNode(fosm,-10,0,lon0 - dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,0,lon0 + dlon/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-12\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"name\" v=\"name\"/>\n")
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2), lat0 - dlat/2*1.5, (lon0 + dlon/2), lat0 + dlat/2*1.5)
        return strOSm, bbox
    #
    if elementType == 'lineshield':
        insertNode(fosm,-10,0,lon0 - dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,0,lon0 + dlon/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-12\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"ref\" v=\"ref\"/>\n")
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2), lat0 - dlat/2*1.5, (lon0 + dlon/2), lat0 + dlat/2*1.5)
        return strOSm, bbox
    #
    if elementType == 'rectangle':
        insertNode(fosm,-10,lat0 + dlat/2,lon0 - dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,lat0 + dlat/2,lon0 + dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-12,lat0 - dlat/2,lon0 + dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-13,lat0 - dlat/2,lon0 - dlon/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-14\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n\
         <nd ref=\"-12\" />\n\
         <nd ref=\"-13\" />\n\
         <nd ref=\"-10\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"is_area\" v=\"yes\"/>\n")
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2)*1.5, (lat0 - dlat/2)*1.5, (lon0 + dlon/2)*1.5, (lat0 + dlat/2)*1.5)
        return strOSm, bbox
    #
    if elementType == 'rectangletext':
        insertNode(fosm,-10,lat0 + dlat/2,lon0 - dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,lat0 + dlat/2,lon0 + dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-12,lat0 - dlat/2,lon0 + dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-13,lat0 - dlat/2,lon0 - dlon/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-14\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n\
         <nd ref=\"-12\" />\n\
         <nd ref=\"-13\" />\n\
         <nd ref=\"-10\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"name\" v=\"name\"/>\n")
        fosm.write( "    <tag k=\"is_area\" v=\"yes\"/>\n")
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2)*1.5, (lat0 - dlat/2)*1.5, (lon0 + dlon/2)*1.5, (lat0 + dlat/2)*1.5)
        return strOSm, bbox
    #
    if elementType == 'rectanglepoint':
        insertNode(fosm,-10,lat0 + dlat/2,lon0 - dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,lat0 + dlat/2,lon0 + dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-12,lat0 - dlat/2,lon0 + dlon/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-13,lat0 - dlat/2,lon0 - dlon/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-14\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n\
         <nd ref=\"-12\" />\n\
         <nd ref=\"-13\" />\n\
         <nd ref=\"-10\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"is_area\" v=\"yes\"/>\n")
        fosm.write("  </way>\n")
        insertNode(fosm,-13,lat0 ,lon0)
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write("  </node>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2)*1.5, (lat0 - dlat/2)*1.5, (lon0 + dlon/2)*1.5, (lat0 + dlat/2)*1.5)
        return strOSm, bbox
    #
    if elementType == 'square':
        insertNode(fosm,-10,lat0 + dlat/2,lat0 - dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,lat0 + dlat/2,lat0 + dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-12,lat0 - dlat/2,lat0 + dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-13,lat0 - dlat/2,lat0 - dlat/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-14\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n\
         <nd ref=\"-12\" />\n\
         <nd ref=\"-13\" />\n\
         <nd ref=\"-10\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"is_area\" v=\"yes\"/>\n")
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2)*1.5, (lat0 - dlat/2)*1.5, (lon0 + dlon/2)*1.5, (lat0 + dlat/2)*1.5)
        return strOSm, bbox
    #
    if elementType == 'squaretext':
        insertNode(fosm,-10,lat0 + dlat/2,lon0 - dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,lat0 + dlat/2,lon0 + dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-12,lat0 - dlat/2,lon0 + dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-13,lat0 - dlat/2,lon0 - dlat/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-14\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n\
         <nd ref=\"-12\" />\n\
         <nd ref=\"-13\" />\n\
         <nd ref=\"-10\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"name\" v=\"name\"/>\n")
        fosm.write( "    <tag k=\"is_area\" v=\"yes\"/>\n")
        fosm.write("  </way>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2)*1.5, (lat0 - dlat/2)*1.5, (lon0 + dlon/2)*1.5, (lat0 + dlat/2)*1.5)
        return strOSm, bbox
    #
    if elementType == 'squarepoint':
        insertNode(fosm,-10,lat0 + dlat/2,lon0 - dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-11,lat0 + dlat/2,lon0 + dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-12,lat0 - dlat/2,lon0 + dlat/2)
        fosm.write("  </node>\n")
        insertNode(fosm,-13,lat0 - dlat/2,lon0 - dlat/2)
        fosm.write("  </node>\n")
        fosm.write("  <way id=\"-14\" visible=\"true\">\n\
         <nd ref=\"-10\" />\n\
         <nd ref=\"-11\" />\n\
         <nd ref=\"-12\" />\n\
         <nd ref=\"-13\" />\n\
         <nd ref=\"-10\" />\n")
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write( "    <tag k=\"is_area\" v=\"yes\"/>\n")
        fosm.write("  </way>\n")
        insertNode(fosm,-13,lat0 ,lon0)
        for t in tagList:
            fosm.write( "    <tag k=\"%s\" v=\"%s\"/>\n" % (getTagKey(t), getTagValue(t)))
        fosm.write("  </node>\n")
        fosm.write("</osm>")
        strOSm = fosm.getvalue()
        fosm.close()
        bbox=((lon0 - dlon/2)*1.5, (lat0 - dlat/2)*1.5, (lon0 + dlon/2)*1.5, (lat0 + dlat/2)*1.5)
        return strOSm, bbox
    #
    return True
##,"[tunnel]=''","[bridge]=''","[tracktype]='grade2'","[amenity]='place_of_worship'"
def test():
    """ Called if the script is launched from command line
    """
    renderLegendElement("osm_full.xml", 'line',\
     ["[highway]='primary'"],\
      18, 50, 'output.png')
#
def renderLegendElement(inputstylesheet, elementType, tagList, zoom, imageWidth, map_uri):
    # the mapfile (stylesheet made only for legend element rendering
    # is returned as a string, no file is written on disk
    # then use mapnik.load_map_from_string
    mapfile = create_legend_stylesheet(inputstylesheet)
    
    # create a new element, which return its bbox and an osm file as
    # a string
    osmStr, bound = createOsmElement(elementType, tagList, zoom)
    # create a named temporary file
    # l.datasource = Osm(file=osmFile.name) needs a real file 
    # we cannot pass a StringIO nor a string, nor a unnammed
    # temporary file
    osmFile = tempfile.NamedTemporaryFile(mode='w+t')
    osmFile.write(osmStr) #write the osm file
    osmFile.seek(0) #rewind
    
    #---------------------------------------------------
    # Set up projection
    # long/lat in degrees, aka ESPG:4326 and "WGS 84" 
    lonlat = mapnik.Projection('+proj=longlat +datum=WGS84')

    #bbbox =(lon,lat,maxlon,maxlat)
    ratio= abs((bound[2]-bound[0])/(bound[3]-bound[1]))
    width = imageWidth
    height = int(width/ratio*1) 
    # add +1 if highway=path looks blurry FIXME
    
    m = mapnik.Map(width,height)
    
    mapnik.load_map_from_string(m,mapfile)
    
    m.srs = lonlat.params()
    for l in m.layers:
        l.datasource = Osm(file=osmFile.name)
        l.srs = lonlat.params()
    
    # uncomment this line to save the mapfile on disk, remember to 
    # NEVER show this file to a mapfile maintainer:
    #save_map(m,'mapfile.xml')
    
    
    # render the element and save to disk
    bbox =lonlat.forward(mapnik.Envelope(mapnik.Coord(bound[0],bound[1]),\
     mapnik.Coord(bound[2],bound[3])))
    m.zoom_to_box(bbox)
    im = mapnik.Image(width,height)
    mapnik.render(m, im)
    osmFile.close() # closing the datasource
    view = im.view(0,0,width,height) # x,y,width,height
    #print "saving ", map_uri
    #view.save(map_uri,'png')
    
    #'save' the image in a string
    imgStr=view.tostring('png')
    
    # reopen the saved image with PIL to count the color
    # if 1, the pic is empty 
    #img = Image.open(map_uri)
    
    # kind of StringIO() for images instead:
    imgParser=ImageFile.Parser()
    imgParser.feed(imgStr)
    img = imgParser.close()
    
    if len(img.getcolors()) == 1:
        print "empty file not saved", map_uri
        #delete the pic file if empty
        #os.remove(map_uri)
    else:
        # Crop the file to its smaller extent
        # Cropping the pic allow a much concise html page formatting,
        # use CSS for the rest
        img256=img.convert('L')
        imgbg=ImageChops.constant(img256,img256.getpixel((0,0)))
        box=ImageChops.difference(img256, imgbg).getbbox()
        out=img.crop(box)
        print "saving ", map_uri
        out.save(map_uri)
        
    return True

#
if __name__ == "__main__":
    test()


