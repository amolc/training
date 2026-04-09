from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Stock
from .serializers import StockSerializer


class Stocks(APIView):
    def get(self, request, pk=None, format=None):
        if pk is not None:
            stock = get_object_or_404(Stock._default_manager, pk=pk)
            serializer = StockSerializer(stock)
            print("line 15",serializer.data)
            return Response(serializer.data)

        stocks = Stock._default_manager.all()
        print("line 18",stocks)
        serializer = StockSerializer(stocks, many=True)
        print("line 22",serializer.data)
        return Response(serializer.data)

    def post(self, request, format=None):
        print("line no 22", request.data)
        serializer = StockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request, pk, format=None):
        stock = get_object_or_404(Stock._default_manager, pk=pk)
        serializer = StockSerializer(stock, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk, format=None):
        stock = get_object_or_404(Stock._default_manager, pk=pk)
        stock.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk, format=None):
        stock = get_object_or_404(Stock._default_manager, pk=pk)
        serializer = StockSerializer(stock, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
