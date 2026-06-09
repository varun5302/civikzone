from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.forms import PasswordResetForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import CustomUser
from datetime import date
import re


class CitizenPasswordResetForm(PasswordResetForm):
    """Password reset form that allows active citizen accounts, including social-login users."""

    def get_users(self, email):
        UserModel = get_user_model()
        return UserModel._default_manager.filter(
            email__iexact=email,
            is_active=True,
            role='user',
        )

def _apply_profile_widget_classes(form):
    """Apply consistent Bootstrap classes so template CSS can style fields."""
    for name, field in form.fields.items():
        widget = field.widget
        existing = widget.attrs.get('class', '')

        if isinstance(widget, forms.Select):
            base_class = 'form-select'
        else:
            base_class = 'form-control'

        widget.attrs['class'] = f"{existing} {base_class}".strip()

        if name == 'date_of_birth':
            widget.attrs['type'] = 'date'

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'phone', 'first_name', 'last_name')

class CustomUserChangeForm(UserChangeForm):
    password = None  # Remove password field from form
    
    class Meta:
        model = CustomUser
        fields = (
            'first_name', 'last_name', 'email', 'phone', 
            'profile_picture', 'date_of_birth', 'gender',
            'address', 'landmark', 'city', 'state', 'pincode',
            'aadhar_number', 'pan_number',
            'alternate_phone', 'emergency_contact', 'emergency_contact_name'
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_profile_widget_classes(self)
    
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                raise ValidationError('You must be at least 18 years old.')
            if age > 120:
                raise ValidationError('Please enter a valid date of birth.')
        return dob
    
    def clean_aadhar_number(self):
        aadhar = self.cleaned_data.get('aadhar_number')
        if aadhar:
            if not re.match(r'^\d{12}$', aadhar):
                raise ValidationError('Aadhar number must be 12 digits.')
            
            # Check for duplicate (excluding current user)
            qs = CustomUser.objects.filter(aadhar_number=aadhar)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('This Aadhar number is already registered.')
        
        return aadhar
    
    def clean_pan_number(self):
        pan = self.cleaned_data.get('pan_number')
        if pan:
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan.upper()):
                raise ValidationError('PAN number must be 10 characters (5 letters, 4 digits, 1 letter).')
            
            # Check for duplicate
            qs = CustomUser.objects.filter(pan_number__iexact=pan)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('This PAN number is already registered.')
            
            return pan.upper()
        
        return pan
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            if not re.match(r'^\d{10}$', phone):
                raise ValidationError('Phone number must be 10 digits.')
        return phone
    
    def clean_pincode(self):
        pincode = self.cleaned_data.get('pincode')
        if pincode:
            if not re.match(r'^\d{6}$', pincode):
                raise ValidationError('Pincode must be 6 digits.')
        return pincode


class AdminUserChangeForm(CustomUserChangeForm):
    """Admin-only form for editing user role and assignment fields."""

    class Meta(CustomUserChangeForm.Meta):
        fields = CustomUserChangeForm.Meta.fields + (
            'role', 'department', 'employee_id', 'is_active'
        )

class ProfilePictureForm(forms.ModelForm):
    """Form for updating profile picture only"""
    class Meta:
        model = CustomUser
        fields = ['profile_picture']
    
    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture:
            # Check file size (max 2MB)
            if picture.size > 2 * 1024 * 1024:
                raise ValidationError('Image file too large (max 2MB)')
            
            # Check file type
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            extension = picture.name.split('.')[-1].lower()
            if f'.{extension}' not in valid_extensions:
                raise ValidationError('Unsupported file type. Please upload JPG, JPEG, PNG or GIF.')
        
        return picture

class PasswordChangeForm(forms.Form):
    """Form for changing password"""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Current Password'
        }),
        label='Current Password'
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'New Password'
        }),
        label='New Password',
        min_length=8
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm New Password'
        }),
        label='Confirm New Password'
    )
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise ValidationError('Current password is incorrect.')
        return current_password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        
        # Password strength validation
        if new_password:
            if len(new_password) < 8:
                self.add_error('new_password', 'Password must be at least 8 characters long.')
            if not any(char.isdigit() for char in new_password):
                self.add_error('new_password', 'Password must contain at least one digit.')
            if not any(char.isalpha() for char in new_password):
                self.add_error('new_password', 'Password must contain at least one letter.')


class ProfileResetPasswordForm(forms.Form):
    """Form for resetting password from an emailed link."""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'New Password'
        }),
        label='New Password',
        min_length=8
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm New Password'
        }),
        label='Confirm New Password'
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise ValidationError('Passwords do not match.')

            if len(new_password) < 8:
                raise ValidationError('Password must be at least 8 characters long.')
            if not any(char.isdigit() for char in new_password):
                raise ValidationError('Password must contain at least one digit.')
            if not any(char.isalpha() for char in new_password):
                raise ValidationError('Password must contain at least one letter.')

        return cleaned_data


class OfficerProfileForm(UserChangeForm):
    """Form for officer profile management"""
    password = None  # Remove password field from form
    
    class Meta:
        model = CustomUser
        fields = (
            'first_name', 'last_name', 'email', 'phone', 
            'profile_picture', 'date_of_birth', 'gender',
            'address', 'landmark', 'city', 'state', 'pincode',
            'aadhar_number', 'pan_number',
            'alternate_phone', 'emergency_contact', 'emergency_contact_name',
            # Officer-specific fields
            'department', 'employee_id'
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'employee_id': forms.TextInput(attrs={'readonly': 'readonly'}),  # Read-only for officers
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_profile_widget_classes(self)
    
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                raise ValidationError('You must be at least 18 years old.')
            if age > 120:
                raise ValidationError('Please enter a valid date of birth.')
        return dob
    
    def clean_aadhar_number(self):
        aadhar = self.cleaned_data.get('aadhar_number')
        if aadhar:
            if not re.match(r'^\d{12}$', aadhar):
                raise ValidationError('Aadhar number must be 12 digits.')
            
            qs = CustomUser.objects.filter(aadhar_number=aadhar)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('This Aadhar number is already registered.')
        
        return aadhar
    
    def clean_pan_number(self):
        pan = self.cleaned_data.get('pan_number')
        if pan:
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan.upper()):
                raise ValidationError('PAN number must be 10 characters (5 letters, 4 digits, 1 letter).')
            
            qs = CustomUser.objects.filter(pan_number__iexact=pan)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('This PAN number is already registered.')
            
            return pan.upper()
        
        return pan
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            if not re.match(r'^\d{10}$', phone):
                raise ValidationError('Phone number must be 10 digits.')
        return phone
    
    def clean_pincode(self):
        pincode = self.cleaned_data.get('pincode')
        if pincode:
            if not re.match(r'^\d{6}$', pincode):
                raise ValidationError('Pincode must be 6 digits.')
        return pincode
        
        return cleaned_data

# Admin/Officer Forgot Password Forms
class AdminForgotPasswordForm(forms.Form):
    """Form for admin/officer to enter username or email for password reset"""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username or email'
        }),
        label='Username or Email'
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            user = CustomUser.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username),
                role__in=['administrator', 'officer']
            ).first()
            if not user:
                raise forms.ValidationError('No admin or officer account found with this username or email.')
        return username

class AdminResetPasswordForm(forms.Form):
    """Form for admin/officer to reset password"""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        }),
        label='New Password',
        min_length=8
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        }),
        label='Confirm New Password'
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError('Passwords do not match.')

            # Password strength validation
            if len(new_password) < 8:
                raise forms.ValidationError('Password must be at least 8 characters long.')
            if not any(char.isdigit() for char in new_password):
                raise forms.ValidationError('Password must contain at least one digit.')
            if not any(char.isalpha() for char in new_password):
                raise forms.ValidationError('Password must contain at least one letter.')

        return cleaned_data


class AdminForgotPasswordForm(forms.Form):
    """Form for admin/officer forgot password - username or email input"""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username or email',
            'autocomplete': 'username'
        }),
        label='Username or Email',
        max_length=150
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            user = CustomUser.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username),
                role__in=['administrator', 'officer']
            ).first()
            if not user:
                raise ValidationError('No admin or officer account found with this username or email.')
        return username


class AdminResetPasswordForm(forms.Form):
    """Form for admin/officer password reset"""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        }),
        label='New Password',
        min_length=8
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        }),
        label='Confirm New Password'
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError('Passwords do not match.')

            # Password strength validation
            if len(new_password) < 8:
                raise forms.ValidationError('Password must be at least 8 characters long.')
            if not any(char.isdigit() for char in new_password):
                raise forms.ValidationError('Password must contain at least one digit.')
            if not any(char.isalpha() for char in new_password):
                raise forms.ValidationError('Password must contain at least one letter.')

        return cleaned_data


# Zone Officer Email-based Forgot Password Forms
class OfficerForgotPasswordForm(forms.Form):
    """Form for zone officer to enter email for password reset"""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your registered email address'
        }),
        label='Email Address'
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            users = CustomUser.objects.filter(email=email, role='officer')
            if users.count() == 0:
                raise forms.ValidationError('No Zone Officer account found with this email address.')
            elif users.count() > 1:
                raise forms.ValidationError('Multiple accounts found with this email. Please contact support.')
            # If exactly one, it's valid
        return email


class OfficerResetPasswordForm(forms.Form):
    """Form for zone officer to reset password"""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        }),
        label='New Password',
        min_length=8
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        }),
        label='Confirm New Password'
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise forms.ValidationError('Passwords do not match.')

            # Password strength validation
            if len(new_password) < 8:
                raise forms.ValidationError('Password must be at least 8 characters long.')
            if not any(char.isdigit() for char in new_password):
                raise forms.ValidationError('Password must contain at least one digit.')
            if not any(char.isalpha() for char in new_password):
                raise forms.ValidationError('Password must contain at least one letter.')

        return cleaned_data