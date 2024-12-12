from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from .models import Rule, MainUser, SubUser, Message

class SignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=False, help_text='Optional.')
    last_name = forms.CharField(max_length=30, required=False, help_text='Optional.')
    email = forms.EmailField(max_length=254, help_text='Required. Inform a valid email address.')
    class Meta:
        model = MainUser 
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

class OrderForm(forms.Form):
    items = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}))

class RuleForm(forms.ModelForm):
    class Meta:
        model = Rule
        fields = ['rule', 'weekly_qty', 'daily', 'break_only', 'am_only', 'lunch_only', 'pm_only']
        widgets = {
            'rule': forms.TextInput(attrs={'class': 'custom-input'}),
        }

class InvitationForm(forms.Form):
    email = forms.EmailField()
    role = forms.ModelChoiceField(queryset=Group.objects.none(), label="Role")  # Start with an empty queryset

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the queryset for the role field, excluding the "Owner" role (ID = 1)
        self.fields['role'].queryset = Group.objects.exclude(id=1)

class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']

