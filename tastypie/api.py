import warnings
from django.conf.urls.defaults import *
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from tastypie import _add_resource, _remove_resource
from tastypie.exceptions import NotRegistered
from tastypie.serializers import Serializer
from tastypie.utils.mime import determine_format, build_content_type


class Api(object):
    """
    Implements a registry to tie together the various resources that make up
    an API.
    
    Especially useful for navigation, HATEOAS and for providing multiple
    versions of your API.
    
    Optionally supplying ``api_name`` allows you to name the API. Generally,
    this is done with version numbers (i.e. ``v1``, ``v2``, etc.) but can
    be named any string.
    """
    def __init__(self, api_name="v1"):
        self.api_name = api_name
        self._registry = {}
        self._canonicals = {}
    
    def register(self, resource, canonical=True):
        """
        Registers a ``Resource`` subclass with the API.
        
        Optionally accept a ``canonical`` argument, which indicates that the
        resource being registered is the canonical variant. Defaults to
        ``True``.
        """
        resource_name = getattr(resource, 'resource_name', None)
        
        if resource_name is None:
            raise ImproperlyConfigured("Resource %r must define a 'resource_name'." % resource)
        
        self._registry[resource_name] = resource
        
        if canonical is True:
            if resource_name in self._canonicals:
                warnings.warn("A new resource '%r' is replacing the existing canonical URL for '%s'." % (resource, resource_name), Warning, stacklevel=2)
            
            self._canonicals[resource_name] = resource
        
        # Register it globally so we can build URIs.
        _add_resource(self, resource, canonical)
    
    def unregister(self, resource_name):
        """
        If present, unregisters a resource from the API.
        """
        if resource_name in self._registry:
            _remove_resource(self, self._registry[resource_name])
            del(self._registry[resource_name])
        
        if resource_name in self._canonicals:
            del(self._canonicals[resource_name])
    
    def canonical_resource_for(self, resource_name):
        """
        Returns the canonical resource for a given ``resource_name``.
        """
        if resource_name in self._canonicals:
            return self._canonicals[resource_name]
        
        raise NotRegistered("No resource was registered as canonical for '%s'." % resource_name)
    
    def wrap_view(self, view):
        def wrapper(request, *args, **kwargs):
            return getattr(self, view)(request, *args, **kwargs)
        return wrapper
    
    @property
    def urls(self):
        """
        Provides URLconf details for the ``Api`` and all registered
        ``Resources`` beneath it.
        """
        pattern_list = [
            url(r"^(?P<api_name>%s)/$" % self.api_name, self.wrap_view('top_level'), name="api_%s_top_level" % self.api_name),
        ]
        
        for name in sorted(self._registry.keys()):
            self._registry[name].api_name = self.api_name
            pattern_list.append((r"^(?P<api_name>%s)/" % self.api_name, include(self._registry[name].urls)))
        
        urlpatterns = patterns('',
            *pattern_list
        )
        return urlpatterns
    
    def top_level(self, request, api_name=None):
        """
        A view that returns a serialized list of all resources registers
        to the ``Api``. Useful for discovery.
        """
        serializer = Serializer()
        available_resources = {}
        
        if api_name is None:
            api_name = self.api_name
        
        for name in sorted(self._registry.keys()):
            available_resources[name] = reverse("api_dispatch_list", kwargs={
                'api_name': api_name,
                'resource_name': name,
            })
        
        desired_format = determine_format(request, serializer)
        serialized = serializer.serialize(available_resources, desired_format)
        return HttpResponse(content=serialized, content_type=build_content_type(desired_format))
