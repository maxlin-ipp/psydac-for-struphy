# coding: utf-8

from gelato.expr     import GltExpr as sym_GltExpr

from spl.api.basic         import BasicCodeGen
from spl.api.ast.glt       import GltKernel
from spl.api.ast.glt       import GltInterface
from spl.api.settings      import SPL_BACKEND_PYTHON, SPL_DEFAULT_FOLDER
from spl.api.grid          import CollocationBasisValues

from spl.cad.geometry      import Geometry
from spl.mapping.discrete  import SplineMapping, NurbsMapping


#==============================================================================
class DiscreteGltExpr(BasicCodeGen):

    def __init__(self, expr, *args, **kwargs):
        if not isinstance(expr, sym_GltExpr):
            raise TypeError('> Expecting a symbolic Glt expression')

        if not args:
            raise ValueError('> fem spaces must be given as a list/tuple')

        assert( len(args) == 2 )

        # ...
        domain_h = args[0]
        assert( isinstance(domain_h, Geometry) )

        mapping = list(domain_h.mappings.values())[0]
        self._mapping = mapping

        is_rational_mapping = False
        if not( mapping is None ):
            is_rational_mapping = isinstance( mapping, NurbsMapping )

        self._is_rational_mapping = is_rational_mapping
        # ...

        # ...
        self._spaces = args[1]
        # ...

        # ...
        kwargs['mapping'] = self.spaces[0].symbolic_mapping

        BasicCodeGen.__init__(self, expr, **kwargs)
        # ...

#        print('====================')
#        print(self.dependencies_code)
#        print('====================')
#        print(self.interface_code)
#        print('====================')
##        import sys; sys.exit(0)

    @property
    def mapping(self):
        return self._mapping

    @property
    def spaces(self):
        return self._spaces

    # TODO add comm and treate parallel case
    def _create_ast(self, expr, tag, **kwargs):

        mapping = kwargs.pop('mapping', None)
        backend = kwargs.pop('backend', SPL_BACKEND_PYTHON)

        # ...
        kernel = GltKernel( expr, self.spaces,
                            name = 'kernel_{}'.format(tag),
                            mapping = mapping,
                            backend = backend )

        interface = GltInterface( kernel,
                                  name = 'interface_{}'.format(tag),
                                  mapping = mapping,
                                  backend = backend )
        # ...

        ast = {'kernel': kernel, 'interface': interface}
        return ast


    def _check_arguments(self, **kwargs):

        # TODO do we need a method from Interface to map the dictionary of arguments
        # that are passed for the call (in the same spirit of build_arguments)
        # the idea is to be sure of their order, since they can be passed to
        # Fortran

        _kwargs = {}

        # ... mandatory arguments
        sym_args = self.interface.in_arguments
        keys = [str(a) for a in sym_args]
        for key in keys:
            try:
                _kwargs[key] = kwargs[key]
            except:
                raise KeyError('Unconsistent argument with interface')
        # ...

        # ... optional (inout) arguments
        sym_args = self.interface.inout_arguments
        keys = [str(a) for a in sym_args]
        for key in keys:
            try:
                _kwargs[key] = kwargs[key]
            except:
                pass
        # ...

        return _kwargs

    def evaluate(self, *args, **kwargs):

        kwargs = self._check_arguments(**kwargs)

        # ... TODO
        t1,t2 = args
        # ...

        # ... TODO
        Wh, Vh = self.spaces
        args = args + (Vh,)
        # ...

        # ... TODO add nderiv
        if self.expr.form.fields or self.mapping:
            grid = (t1, t2)
#            basis_values = CollocationBasisValues(grid, Vh, nderiv=0)
            basis_values = CollocationBasisValues(grid, Vh, nderiv=1)
            args = args + (basis_values,)
        # ...

        if self.mapping:
            args = args + (self.mapping,)

        return self.func(*args, **kwargs)
#        return self.func(*newargs, **kwargs)
