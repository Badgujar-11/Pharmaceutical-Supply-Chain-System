from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import CustomUserCreationForm, ProductForm, OrderForm
from .models import CustomUser, Product, Order, TransactionLog
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseRedirect
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def home(request):
    return render(request, 'home.html')

def register(request):
    """
    Register a new user.
    - Admins are auto-approved.
    - Customers need admin approval.
    - All other roles (supplier, distributor, pharmacy) are auto-approved.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # ---- Approval Logic ----
            if user.role == 'admin':
                user.is_approved = True
            elif user.role == 'customer':
                user.is_approved = False
            else:
                # supplier, distributor, pharmacy → auto-approved
                user.is_approved = True

            user.save()
            messages.success(
                request,
                'Registration successful! '
                'Please wait for admin approval if you registered as a customer.'
            )
            return redirect('login')
    else:
        # GET request → fresh form
        form = CustomUserCreationForm()

    # Always pass form to template (GET or failed POST)
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_approved or user.role == 'admin':
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Your account is pending approval.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    # Always pass the form for GET and failed POST
    form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def dashboard(request):
    user = request.user
    context = {'user': user}
    
    if user.role == 'admin':
        # Admin: Pending approvals + recent logs
        context['pending_approvals'] = CustomUser.objects.filter(is_approved=False)
        context['recent_logs'] = TransactionLog.objects.all()[:10]
        context['products'] = Product.objects.all()[:5]
        context['orders'] = Order.objects.all()[:5]
        
    elif user.role in ['supplier', 'manufacturer', 'wholesaler', 'distributor']:
        # Stakeholders: Their products + orders
        context['products'] = Product.objects.filter(created_by=user)
        context['orders'] = Order.objects.filter(Q(from_user=user) | Q(to_user=user))
        
    elif user.role == 'customer':
        # Customers: Their orders only
        context['orders'] = Order.objects.filter(to_user=user)
        
    return render(request, 'dashboard.html', context)

# Product CRUD
@login_required
def product_list(request):
    if request.user.role not in ['admin', 'supplier', 'manufacturer', 'wholesaler', 'distributor']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    products = Product.objects.filter(created_by=request.user) if request.user.role != 'admin' else Product.objects.all()
    return render(request, 'product_list.html', {'products': products})

@login_required
def product_create(request):
    if request.user.role not in ['admin', 'supplier', 'manufacturer', 'wholesaler', 'distributor']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            messages.success(request, 'Product created successfully!')
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'product_form.html', {'form': form, 'action': 'Create'})

@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk, created_by=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully!')
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'product_form.html', {'form': form, 'action': 'Update'})
@login_required
def product_delete(request, pk):
    # Get product (admin can delete any, others only their own)
    product = get_object_or_404(
        Product,
        pk=pk,
        created_by=request.user  # Only owner OR admin below
    ) if request.user.role != 'admin' else get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        product.delete()
        messages.success(request, f"Product '{product.name}' deleted successfully!")
        return redirect('product_list')

    return render(request, 'product_confirm_delete.html', {'product': product})

# Order CRUD
@login_required
def order_list(request):
    if request.user.role == 'admin':
        orders = Order.objects.all()
    elif request.user.role == 'customer':
        orders = Order.objects.filter(to_user=request.user)
    elif request.user.role in ['distributor']:
        # Distributor sees ALL orders (to pick up/deliver)
        orders = Order.objects.all()
    else:
        # Supplier, Manufacturer, Wholesaler
        orders = Order.objects.filter(Q(from_user=request.user) | Q(to_user=request.user))
    
    return render(request, 'order_list.html', {'orders': orders})

@login_required
def order_create(request):
    if request.user.role not in ['manufacturer', 'wholesaler', 'distributor', 'customer']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.from_user = request.user
            order.save()
            TransactionLog.objects.create(order=order, action='Order Created', user=request.user)
            messages.success(request, 'Order placed successfully!')
            return redirect('order_list')
    else:
        form = OrderForm()
    return render(request, 'order_form.html', {'form': form, 'action': 'Create'})

@login_required
def order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)

    # === PERMISSION CHECK: ALLOW admin, from_user, OR distributor ===
    allowed_roles = ['admin', 'distributor']
    if request.user != order.from_user and request.user.role not in allowed_roles:
        messages.error(request, 'Access denied. You do not have permission to update this order.')
        return redirect('order_list')
    
    if request.method == 'POST':
        old_status = order.status  # Save old status
        form = OrderForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save()
            
            # === SEND REAL-TIME NOTIFICATION IF STATUS CHANGED ===
            if old_status != order.status:
                message = f"Order #{order.pk} status updated to '{order.status}'"
                send_notification(order.to_user.id, message, "order_update")
            
            # === BLOCKCHAIN AUDIT LOG ===
            TransactionLog.objects.create(
                order=order,
                action=f"Status Updated from '{old_status}' to '{order.status}'",
                user=request.user
            )
            messages.success(request, 'Order updated successfully!')
            return redirect('order_list')
    else:
        form = OrderForm(instance=order)
    
    return render(request, 'order_form.html', {
        'form': form,
        'action': 'Update',
        'order': order
    })

@login_required
def order_delete(request, pk):  # Cancel order
    order = get_object_or_404(Order, pk=pk, from_user=request.user)
    if request.method == 'POST':
        TransactionLog.objects.create(order=order, action='Order Cancelled', user=request.user)
        order.delete()
        messages.success(request, 'Order cancelled successfully!')
        return redirect('order_list')
    return render(request, 'order_confirm_delete.html', {'order': order})

def is_admin(user):
    return user.is_authenticated and user.role == 'admin'

# --- Admin Approval List View ---
@user_passes_test(is_admin, login_url='dashboard')
def approve_user_list(request):
    pending_users = CustomUser.objects.filter(is_approved=False)
    return render(request, 'approve_user_list.html', {'pending_users': pending_users})

@login_required
def approve_user_list(request):
    if request.user.role != 'admin':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    pending_users = CustomUser.objects.filter(is_approved=False)
    return render(request, 'approvals.html', {'pending_users': pending_users})


@login_required
def approve_user(request, user_id):
    if request.user.role != 'admin':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    user = get_object_or_404(CustomUser, id=user_id, is_approved=False)
    
    if request.method == 'POST':
        user.is_approved = True
        user.save()
        # Inside approve_user view, after user.save():
        send_notification(user.id, f"Your account has been approved! You can now log in.", "approval")
        messages.success(request, f"User '{user.username}' approved!")
    
    return redirect('approve_user_list')  # ← STAYS ON PAGE

def reject_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, is_approved=False)
    if request.method == 'POST':
        user.delete()
        messages.success(request, f'User {user.username} rejected and deleted.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/dashboard/'))


@login_required
def audit_logs(request):
    logs = TransactionLog.objects.all().order_by('-timestamp')
    return render(request, 'audit_logs.html', {'logs': logs})


@login_required
def track_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    
    # Access control: only involved users or admin
    if request.user.role != 'admin' and request.user not in [order.from_user, order.to_user]:
        messages.error(request, "You don't have permission to track this order.")
        return redirect('order_list')
    
    # Get all logs for this order
    logs = TransactionLog.objects.filter(order=order).order_by('timestamp')
    
    return render(request, 'track_order.html', {
        'order': order,
        'logs': logs
    })


def send_notification(user_id, message, type="info"):
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {"type": "send.notification", "message": message, "type": type}
        )