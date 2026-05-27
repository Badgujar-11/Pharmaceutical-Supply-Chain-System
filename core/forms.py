from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Product, Order

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=CustomUser.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2', 'role')

    def clean_email(self):
        email = self.cleaned_data['email']
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email
    
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ('name', 'description')

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ('product', 'quantity', 'to_user', 'transporter', 'status')
        widgets = {
            'status': forms.Select(choices=Order.STATUS_CHOICES),
            'to_user': forms.Select(attrs={'class': 'form-select'}),
        }