from statistics import multimode
from django.core import paginator
from django.shortcuts import render
from rest_framework import viewsets, mixins, filters
from rest_framework import status
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.views import APIView
from django_filters import rest_framework as filters
from django_filters import Filter, FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
import numpy as np
from itertools import chain
from django.http import HttpResponse
from django.core import serializers
from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from django.http import JsonResponse
from bson import ObjectId
import json
from bson import json_util
import pandas as pd
import operator
from django.db.models import Q
from functools import reduce
from django_pandas.io import read_frame
from django.core.paginator import Paginator

# local models
from .models import *
from .serializers import *
from .scripts import *
from .custom_indicators.custom_ind import *
from .multivariate_analysis.dbscan_analysis import *

import time
from django.db import connection

class ListFilter(Filter):
    def filter(self, qs, value):
        print(value)
        if not value:
            return qs

        # For django-filter versions < 0.13, use lookup_type instead of lookup_expr
        self.lookup_expr = 'in'
        values = value.split(',')
        return super(ListFilter, self).filter(qs, values)


class AccommodationFilter(FilterSet):
    ids = ListFilter(field_name='id')
    crop_name = ListFilter(field_name='crop__name')
    country_name = ListFilter(field_name='country_name')
    name = ListFilter(field_name='name')
    samp_stat = ListFilter(field_name='samp_stat')
    institute_fullname = ListFilter(field_name='institute_fullname')
    geo_lon = ListFilter(field_name='geo_lon')
    geo_lat = ListFilter(field_name='geo_lat')
    taxonomy_taxon_name = ListFilter(field_name='taxonomy_taxon_name')

    class Meta:
        model = Accession
        fields = ['ids', 'crop_name', 'name', 'country_name',
                  'samp_stat', 'institute_fullname', 'geo_lon', 'geo_lat', 'taxonomy_taxon_name']


class AccessionsList(mixins.CreateModelMixin,
                     mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     viewsets.GenericViewSet):
    queryset = Accession.objects.all()
    serializer_class = AccessionsSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = AccommodationFilter
    """ filterset_fields = ['crop', 'name', 'country_name',
                        'samp_stat', 'institute_fullname', 'institute_acronym', 'geo_lon', 'geo_lat', 'taxonomy_taxon_name'] """


class CropList(mixins.CreateModelMixin,
               mixins.ListModelMixin,
               mixins.RetrieveModelMixin,
               mixins.UpdateModelMixin,
               viewsets.GenericViewSet):
    queryset = Crops.objects.all()
    serializer_class = CropsSerializer


class IndicatorViewSet(mixins.CreateModelMixin,
                       mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin,
                       viewsets.GenericViewSet):
    """ View to query indciators """
    queryset = Indicator.objects.all()
    serializer_class = IndicatorsSerializer

    def list(self, request, *args, **kwargs):
        indicator = self.queryset
        serializer = self.serializer_class(indicator, many=True)
        return Response(serializer.data)

def chunked_iterator(queryset, chunk_size=10000):
    paginator = Paginator(queryset, chunk_size)
    for page in range(1, paginator.num_pages + 1):
        for obj in paginator.page(page).object_list:
            yield obj

class IndicatorValViewSet(mixins.CreateModelMixin,
                          mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin,
                          viewsets.GenericViewSet):
    """ View to query indciators """
    queryset = IndicatorValue.objects.all()
    serializer_class = IndicatorValuesSerializer

    def create(self, request, *args, **kwargs):
        start = time.time()
        data = request.data['data']
        #minp = request.data['minp']
        #eps = request.data['eps']
        lst = []
        lst_t = []
        lst_final = []
        lst_cellids = []
        #months = 12
        #periods = data[0]['period']
        #print(periods[0])
        #print(periods[1])
        #for i in range(periods[0], periods[1]):
            #months = months+12

        #print(months)
        #queryset = IndicatorValue.objects.all()
        #query_indicators = Indicator.objects.all()
        # Loop to search indicators selected
        for prop in data:
            print(prop['indicator_name'])
            query_indicator = Indicator.objects.filter(name=prop['indicator_name']).first()
            # queryset to get indicators period selected
            query_period = IndicatorPeriod.objects.filter(period__range=prop['period'], indicator=query_indicator._id)
            #Loop to search the values for each indicator and period
            for qp in query_period:
                print("period:",qp.period)
                id_indicator_period = [Q(**{'indicator_period':qp._id})]
                # Build the query from parameters in the request
                filter_clauses = [Q(**{filter:prop[filter]}) for filter in prop if "month" in str(filter)]
                finished = id_indicator_period + filter_clauses
                if finished:
                    # Queryset with the indicator values response
                    queryset =  IndicatorValue.objects.prefetch_related('indsper').filter(reduce(operator.and_, finished)).count()                    
                    paginator = Paginator(queryset,500)
                    page = paginator.page(1)
                    #serializer = IndicatorValuesSerializer(page, many=True)
                    #print(serializer.data
                    for values in page:
                        lst.append(values)
                        if values.cellid not in lst_cellids:
                            lst_cellids.append(values.cellid)
                    lst_t.append(lst_cellids)
                lst_cellids = []
        a = set(lst_t[0]).intersection(*lst_t[1:])
        for i in lst:
            if i.cellid in a:
                lst_final.append(i)
        serializer = self.serializer_class(lst_final, many=True)
        serializer_list = {
            'data': serializer.data, 'cellids': lst_cellids}
        analysis = dbscan_analysis(serializer_list,12,1)
        result = analysis.to_json(orient = "records")
        parsed = json.loads(result)
        serializer_list = {
            'data': serializer.data, 'cellids': a, 'multivariety': parsed}
        content = {
            'status': 1,
            'responseCode': status.HTTP_200_OK,
            'data': serializer_list,
        }
        return Response(content) 
        """ serializer = self.serializer_class(lst, many=True)
        serializer_list = {
            'data': serializer.data, 'cellids': lst_cellids}
        content = {
            'status': 1,
            'responseCode': status.HTTP_200_OK,
            'data': serializer_list,
        } """
            #if filter_clauses:
                #queryset = queryset.filter(reduce(operator.and_, filter_clauses))
                # Searching indicators values 
        """ print(filter_clauses)
                print(IndicatorValue.objects.filter(reduce(operator.and_, filter_clauses)).query)
                queryset = IndicatorValue.objects.filter(reduce(operator.and_, filter_clauses))
                for values in queryset:
                    lst.append(values)
                    if values.cellid not in lst_cellids:
                        lst_cellids.append(values.cellid)
                lst_t.append(lst_cellids)
                lst_cellids = [] """
        """ end = time.time()
        print("Checking parameters: ", str(end - start))
        start = time.time()
        a = set(lst_t[0]).intersection(*lst_t[1:])
        for i in lst:
            if i.cellid in a:
                lst_final.append(i) 
        end = time.time()
        print("Searching cell ids: ", str(end - start))
        start = time.time()
        serializer = self.serializer_class(lst_final, many=True)
        serializer_list = {
            'data': serializer.data, 'cellids': lst_cellids}
        end = time.time()
        print("Preparing data for dbscan: ", str(end - start))
        start = time.time()
        analysis = dbscan_analysis(serializer_list,12,1)
        end = time.time()
        print("DBscan: ", str(end - start))
        start = time.time()
        result = analysis.to_json(orient = "records")
        parsed = json.loads(result)
        serializer_list = {
            'data': serializer.data, 'cellids': a, 'multivariety': parsed}
        content = {
            'status': 1,
            'responseCode': status.HTTP_200_OK,
            'data': serializer_list,
        }
        end = time.time()
        print("Serialize output: ", str(end - start))
        start = time.time() """


@csrf_exempt
@api_view(('POST',))
def get_custom_indicator(request):
    """ Proccessing custom data """
    # value= request.POST['test']
    data = request.data['data']
    var = request.data['vars']
    data = data[:-1]
    df = pd.DataFrame(data)
    detail = calculate_summary(df, var)
    accessions = merge_data(df, 'IG', 'id')
    serializer = AccessionsSerializer(accessions, many=True)
    print(serializer.data)
    serializer_list = {
        'accessions': serializer.data, 'stats': detail}
    content = {
        'status': 1,
        'responseCode': status.HTTP_200_OK,
        'data': serializer_list,
    }
    return Response(content)


class IndicatorPostViewSet(mixins.CreateModelMixin,
                           mixins.ListModelMixin,
                           mixins.RetrieveModelMixin,
                           mixins.UpdateModelMixin,
                           viewsets.GenericViewSet):
    """ View to query indciators """
    queryset = Accession.objects.all()
    serializer_class = AccessionsSerializer

    def create(self, request, *args, **kwargs):

        # request indicator data
        data = self.request.data['data']
        lst_accessions = []
        lst_cellid = []
        for props in data:
            indicator_qs = Indicator.objects.filter(
                name=props['indicator']).first()
            indicator_period_qs = IndicatorPeriod.objects.filter(
                indicator=indicator_qs._id, period__range=props['period'])
            for ind_per in indicator_period_qs:
                queryIndicator = IndicatorValue.objects.filter(
                    value__range=[props['value']['minValue'], props['value']['highValue']], month__in=props['months'], indicator_period=ind_per._id)
                for ind_val in queryIndicator:
                    lst_accessions.append(ind_val)
                    if ind_val.cellid not in lst_cellid:
                        lst_cellid.append(ind_val.cellid)
        serializer_indicator_value = IndicatorValuesSerializer(
            lst_accessions, many=True)
        serializer_list = {
            'data': serializer_indicator_value.data, 'cellids': lst_cellid}
        content = {
            'status': 1,
            'responseCode': status.HTTP_200_OK,
            'data': serializer_list,
        }
        return Response(content)
        """ month = self.request.data['month']
        value = self.request.data['value']
        indicator = self.request.data['indicator']
        period = self.request.data['period']
        lst = []
        lst_accessions = []
        lst_indicator_period = []
        lst_indicator = []
        indicator_qs = ''
        indicator_period_qs = ''

        if (month == ""):
            queryIndicator = IndicatorValue.objects.filter(
                value__lte=value).iterator()
            for value in queryIndicator:
                accessions = self.queryset.filter(cellid=value.cellid)
                for acces in accessions:
                    lst.append(acces)
            serializer = self.serializer_class(lst, many=True)
            return Response(serializer.data)
        # indicator = Indicator.objects.filter()
        if (month != ""):
            # indicator queryset
            print(indicator)
            indicator_qs = Indicator.objects.filter(name__in=indicator)
            ind_list = list(indicator_qs)
            ind_list.sort(key=lambda indic: indicator.index(indic.name))
            # indicator_period queryset
            if "," in period:
                periods = period.split(",")
                for lst_ind in ind_list:
                    print(lst_ind._id)
                    indicator_period_qs = IndicatorPeriod.objects.filter(
                            indicator=lst_ind._id, period__in=periods)
                    lst_indicator_period.append(indicator_period_qs)

            elif "-" in period:
                periods = period.split("-")
                min_period = periods[0]
                max_period = periods[1]
                for lst_ind in ind_list:
                    indicator_period_qs = IndicatorPeriod.objects.filter(
                        indicator=lst_ind._id, period__range=(min_period, max_period))

            # indicator_value queryset
            min_value = float(value[0])
            max_value = float(value[1])

            for pe in lst_indicator_period:
                for p in pe:
                    print(p.period)
                    queryIndicator = IndicatorValue.objects.filter(
                        value__range=(min_value, max_value), month__in=month, indicator_period=p._id)
                    for values in queryIndicator:
                        lst_accessions.append(values)
            # iterating indicator_value queryset
            lst_cellid = []
            for value in lst_accessions:
                # accessions queryset
                if value.cellid not in lst_cellid:
                    lst_cellid.append(value.cellid)
            # accessions serializer
            accessiones = self.queryset.filter(
                cellid__in=lst_cellid)
            serializer = self.serializer_class(accessiones, many=True)
            serializer_indicator_value = IndicatorValuesSerializer(
                lst_accessions, many=True)
            serializer_list = [serializer.data,
                               serializer_indicator_value.data]
            content = {
                'status': 1,
                'responseCode': status.HTTP_200_OK,
                'data': serializer_list,
            }
            return Response(content) """
