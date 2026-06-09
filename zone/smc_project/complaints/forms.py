from django import forms
from .models import Complaint
import re

def get_subcategories_by_category():
    """Return subcategories grouped by category"""
    return {
        '1. Water Supply': [
            'No water supply',
            'Leaking pipes',
            'Low water pressure',
            'Contaminated water',
            'Issues with water meters',
            'Repair of standposts or handpumps',
            'Illegal water connections',
        ],
        '2. Drainage & Stormwater': [
            'Overflowing or choked drainage',
            'Broken or open manholes',
            'Leakage in main drainage pipelines',
            'Overflowing soak pits or septic tanks',
            'Stormwater logging on public roads or open plots',
        ],
        '3. Health & Hospitals/Dispensaries': [
            'Issues with hospital facilities',
            'Medical waste management',
            'Sanitation issues in hospitals',
            'Water supply issues in hospitals',
            'Power supply issues in hospitals',
        ],
        '4. Public Toilets': [
            'Non-functional toilets',
            'Lack of water supply',
            'Poor maintenance',
            'Lack of cleanliness',
            'Broken doors/locks',
            'No electricity',
        ],
        '5. Food Hygiene': [
            'Unhygienic food preparation',
            'Expired food items',
            'Lack of proper storage',
            'Pest infestation',
            'Improper waste disposal',
        ],
        '6. Streetlights & Roads': [
            'Non-functional streetlights',
            'Damaged roads/potholes',
            'Broken traffic signals',
            'Missing road signs',
            'Encroachment on roads',
            'Illegal parking',
        ],
        '7. Solid Waste': [
            'Irregular garbage collection',
            'Overflowing garbage bins',
            'Illegal dumping',
            'Lack of waste segregation',
            'Open waste burning',
        ],
        '8. Parks & Gardens': [
            'Poor maintenance',
            'Lack of cleanliness',
            'Broken playground equipment',
            'Water supply issues',
            'Encroachment',
            'Lack of security',
        ],
        '9. Civic Centers': [
            'Poor maintenance',
            'Lack of cleanliness',
            'Infrastructure issues',
            'Lack of security',
            'Water supply issues',
            'Power supply issues',
        ],
        '10. Miscellaneous': [
            'Other civic issues',
        ],
    }

class ComplaintForm(forms.ModelForm):
    phone = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'pattern': '[0-9]{10}',
            'title': 'Please enter a valid 10-digit phone number',
            'placeholder': 'Enter your 10-digit phone number'
        })
    )
    
    proof_image = forms.ImageField(
        required=False,  # Will be set dynamically
        widget=forms.FileInput(attrs={
            'accept': 'image/*',
            'capture': 'environment',
            'class': 'form-control d-none',  # Hidden visually
            'id': 'id_proof_image_hidden',
        })
    )
    
    class Meta:
        model = Complaint
        fields = [
            'category', 'other_category', 'subcategory',
            'zone', 'location', 'address', 'latitude', 'longitude', 
            'description', 'phone', 'proof_image'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter your full address (optional)'}),
            'category': forms.Select(attrs={'onchange': 'handleCategoryChange()'}),
            'subcategory': forms.Select(attrs={'onchange': 'handleSubcategoryChange()'}),
            'zone': forms.Select(attrs={'onchange': 'updateWardOptions()'}),
            'location': forms.TextInput(attrs={'placeholder': 'Enter location (optional)'}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial values for category and subcategory if they are custom
        if self.instance:
            if self.instance.category not in dict(Complaint.CATEGORY_CHOICES):
                self.initial['category'] = 'Other'
                self.initial['other_category'] = self.instance.category
            
            # Subcategory is now always from predefined list
            # Make proof_image not required for existing complaints that already have an image
            if self.instance.pk and self.instance.proof_image:
                self.fields['proof_image'].required = False
            else:
                self.fields['proof_image'].required = True
                self.fields['proof_image'].widget.attrs['required'] = 'required'
    
    def get_standard_subcategories(self):
        """Return list of all standard subcategories"""
        standard_subcats = []
        for category, subcats in get_subcategories_by_category().items():
            standard_subcats.extend(subcats)
        return standard_subcats
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        # Remove any non-digit characters
        phone = re.sub(r'\D', '', phone)
        
        if len(phone) != 10:
            raise forms.ValidationError('Please enter a valid 10-digit phone number')
        
        return phone
    
    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        other_category = cleaned_data.get('other_category')
        
        # Validate category
        if category == 'Other' and not other_category:
            self.add_error('other_category', 'Please specify the category')
        elif category == 'Other' and other_category:
            cleaned_data['category'] = other_category
        
        # Subcategory is now always from predefined list, no validation needed
        
        return cleaned_data