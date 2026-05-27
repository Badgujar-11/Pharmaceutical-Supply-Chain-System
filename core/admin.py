# core/admin.py

from django.contrib import admin
from .models import CustomUser, Product, Order, TransactionLog

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'is_approved']
    list_filter = ['role', 'is_approved']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'product', 'from_user', 'to_user', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['product__name', 'id']

    # FIXED: Avoid super()
    def get_queryset(self, request):
        qs = admin.ModelAdmin.get_queryset(self, request)  # ← DIRECT CALL
        if request.user.role == 'supplier':
            return qs.filter(from_user=request.user)
        elif request.user.role == 'distributor':
            return qs.filter(to_user=request.user)
        return qs

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ['order', 'action', 'user', 'timestamp', 'hash_value']
    list_filter = ['action', 'timestamp']
    search_fields = ['action', 'user__username']
    readonly_fields = ['hash_value', 'prev_hash', 'timestamp']

    def chain_valid(self, obj):
        return obj.verify_chain()
    chain_valid.boolean = True
    chain_valid.short_description = "Chain Valid"