
from collections import OrderedDict
from itertools import groupby
import string
import random
import numpy as np

from sympy import Basic
from sympy import symbols, Symbol, IndexedBase, Indexed, Function
from sympy import Mul, Add, Tuple
from sympy import Matrix, ImmutableDenseMatrix
from sympy import sqrt as sympy_sqrt
from sympy import S as sympy_S
from sympy import simplify, expand
from sympy.core.numbers import ImaginaryUnit

from pyccel.ast.core import Variable, IndexedVariable
from pyccel.ast.core import For
from pyccel.ast.core import Assign
from pyccel.ast.core import AugAssign
from pyccel.ast.core import Slice
from pyccel.ast.core import Range
from pyccel.ast.core import FunctionDef
from pyccel.ast.core import FunctionCall
from pyccel.ast import Zeros
from pyccel.ast import Import
from pyccel.ast import DottedName
from pyccel.ast import Nil
from pyccel.ast import Len
from pyccel.ast import If, Is, Return
from pyccel.ast import String, Print, Shape
from pyccel.ast import Comment, NewLine
from pyccel.ast.core      import _atomic

from sympde.core import Constant
from sympde.topology import ScalarField, VectorField
from sympde.topology import IndexedVectorField
from sympde.topology import Mapping
from sympde.expr import BilinearForm
from sympde.core.math import math_atoms_as_str
from sympde.topology.derivatives import _partial_derivatives
from sympde.topology.derivatives import _logical_partial_derivatives
from sympde.topology.derivatives import get_max_partial_derivatives
from sympde.topology.derivatives import print_expression
from sympde.topology.derivatives import get_atom_derivatives
from sympde.topology.derivatives import get_index_derivatives
from sympde.topology import LogicalExpr
from sympde.topology import SymbolicExpr
from sympde.topology import SymbolicDeterminant

#from gelato.core import gelatize

from gelato.glt import BasicGlt
from gelato.expr import gelatize

from .basic import SplBasic
from .utilities import random_string
from .utilities import build_pythran_types_header, variables
from .utilities import is_vector_field, is_field, is_mapping
#from .evaluation import EvalArrayVectorField
from .evaluation import EvalArrayMapping, EvalArrayField


class GltKernel(SplBasic):

    def __new__(cls, expr, spaces, name=None, mapping=None, is_rational_mapping=None, backend=None):

        tag = random_string( 8 )
        obj = SplBasic.__new__(cls, tag, name=name,
                               prefix='kernel', mapping=mapping,
                               is_rational_mapping=is_rational_mapping)

        obj._expr = expr
        obj._spaces = spaces
        obj._eval_fields = None
        obj._eval_mapping = None
        obj._user_functions = []
        obj._backend = backend

        obj._func = obj._initialize()

        return obj

    @property
    def expr(self):
        return self._expr

    @property
    def form(self):
        return self.expr.form

    @property
    def spaces(self):
        return self._spaces

    @property
    def n_rows(self):
        return self._n_rows

    @property
    def n_cols(self):
        return self._n_cols

    # needed for MPI comm => TODO improve BasicCodeGen
    @property
    def max_nderiv(self):
        return None

    @property
    def with_coordinates(self):
        return self._with_coordinates

    @property
    def coordinates(self):
        return self._coordinates

    @property
    def constants(self):
        return self.expr.constants

    @property
    def fields(self):
        return self.expr.fields

    @property
    def fields_coeffs(self):
        return self._fields_coeffs

    @property
    def mapping_coeffs(self):
        if not self.eval_mapping:
            return ()

        return self.eval_mapping.mapping_coeffs

    @property
    def mapping_values(self):
        if not self.eval_mapping:
            return ()

        return self.eval_mapping.mapping_values

    @property
    def eval_fields(self):
        return self._eval_fields

    @property
    def eval_mapping(self):
        return self._eval_mapping

    @property
    def global_mats(self):
        return self._global_mats

    @property
    def global_mats_types(self):
        return self._global_mats_types

    @property
    def user_functions(self):
        return self._user_functions

    @property
    def backend(self):
        return self._backend

    def build_arguments(self, data):

        other = data

        if self.constants:
            other = other + self.constants

        return self.basic_args + other

    def _initialize(self):
        form    = self.form
        dim     = self.expr.ldim
        mapping = self.mapping

        # ... discrete values
        Vh, Wh = self.spaces

        n_elements = Vh.ncells
        degrees    = Vh.degree
        # ...

        # recompute the symbol
        expr = gelatize(form, degrees=degrees, n_elements=n_elements,
                        mapping=mapping, evaluate=True, human=True)

        fields = form.fields
        fields = sorted(fields, key=lambda x: str(x.name))
        fields = tuple(fields)

        # TODO improve
        if mapping is None:
            mapping = ()
#        if self.mapping: mapping = Symbol('mapping')

#        #*************************************
#        # TODO must be moved to __call__ of GltExpr
#        #*************************************
#        # ... TODO must be moved to __call__ of GltExpr
#        ns = ['nx', 'ny', 'nz'][:dim]
#        ns = [Symbol(i, integer=True) for i in ns]
#
#        if isinstance(n_elements, int):
#            n_elements = [n_elements]*dim
#
#        if not( len(ns) == len(n_elements) ):
#            raise ValueError('Wrong size for n_elements')
#
#        for n,v in zip(ns, n_elements):
#            expr = expr.subs(n, v)
#        # ...
#
#        # ...
#        ps = ['px', 'py', 'pz'][:dim]
#        ps = [Symbol(i, integer=True) for i in ps]
#
#        if isinstance(degrees, int):
#            degrees = [degrees]*dim
#
#        if not( len(ps) == len(degrees) ):
#            raise ValueError('Wrong size for degrees')
#
#        d_degrees = {}
#        for p,v in zip(ps, degrees):
#            d_degrees[p] = v
#
#        atoms = list(self.expr.expr.atoms(BasicGlt))
#        for a in atoms:
#            func = a.func
#            p,t = a._args[:]
#            newargs = (d_degrees[p], t)
#            newa = func(*newargs)
#            expr = expr.subs(a, newa)
#        # ...
#        #*************************************

        expr = expand(expr)
        expr = expr.evalf()

#        if mapping:
#            expr = simplify(expr)
        # ...

        # ...
        n_rows = 1 ; n_cols = 1
        if isinstance(expr, (Matrix, ImmutableDenseMatrix)):
            n_rows = expr.shape[0]
            n_cols = expr.shape[1]

        self._n_rows = n_rows
        self._n_cols = n_cols
        # ...

        # ...
        prelude = []
        body = []
        imports = []
        # ...

        # ...
        degrees    = variables('p1:%d'%(dim+1), 'int')
        n_elements = variables('n1:%d'%(dim+1), 'int')
        tis        = variables('t1:%d'%(dim+1), 'real')
        arr_tis    = variables('arr_t1:%d'%(dim+1), dtype='real', rank=1, cls=IndexedVariable)
        xis        = variables('x1:%d'%(dim+1), 'real')
        arr_xis    = variables('arr_x1:%d'%(dim+1), dtype='real', rank=1, cls=IndexedVariable)
        indices    = variables('i1:%d'%(dim+1), 'int')
        lengths    = variables('k1:%d'%(dim+1), 'int')

        ranges     = [Range(lengths[i]) for i in range(dim)]
        # ...

        if fields or mapping:
            basis  = variables( 'basis1:%s'%(dim+1),
                                dtype = 'real',
                                rank = 4,
                                cls = IndexedVariable )

            spans  = variables( 'spans1:%s'%(dim+1),
                                dtype = 'int',
                                rank = 1,
                                cls = IndexedVariable )

        # ...
        self._coordinates = tuple(self.expr.space_variables)
        self._with_coordinates = (len(self._coordinates) > 0)
        # ...

        # ...
        d_symbols = {}
        for i in range(0, n_rows):
            for j in range(0, n_cols):
                is_complex = False
                mat = IndexedBase('symbol_{i}{j}'.format(i=i,j=j))
                d_symbols[i,j] = mat
        # ...

        # ... replace tx/ty/tz by t1/t2/t3
        txs = [Symbol(tx) for tx in ['tx', 'ty', 'tz'][:dim]]
        for ti, tx in zip(tis, txs):
            expr = expr.subs(tx, ti)

        xs = [Symbol(x) for x in ['x', 'y', 'z'][:dim]]
        for xi, x in zip(xis, xs):
            expr = expr.subs(x, xi)
        # ...

        # ...
        atoms_types = (_partial_derivatives,
                       _logical_partial_derivatives,
                       ScalarField,
                       VectorField, IndexedVectorField,
                       SymbolicDeterminant)

        atoms  = _atomic(expr, cls=atoms_types)
        # ...

        # ...
#        atomic_expr_mapping      = [atom for atom in atoms if is_mapping(atom)]
        atomic_expr_field        = [atom for atom in atoms if is_field(atom)]
        atomic_expr_vector_field = [atom for atom in atoms if is_vector_field(atom)]
        # ...

        # ...
#        mapping_expressions = [SymbolicExpr(i) for i in  atomic_expr_mapping]
#        for old, new in zip(atomic_expr_mapping, mapping_expressions):
#            expr = expr.subs(old, new)
        # ...

        # ...
        fields_str    = sorted(tuple(map(print_expression, atomic_expr_field)))
        fields_logical_str = sorted([print_expression(f, logical=True) for f in
                                     atomic_expr_field])
        field_atoms   = tuple(expr.atoms(ScalarField))
        # ...

        # ... create EvalArrayField
        self._eval_fields = []
        self._map_stmts_fields = OrderedDict()
        if atomic_expr_field:
            keyfunc = lambda F: F.space.name
            data = sorted(field_atoms, key=keyfunc)
            for space_str, group in groupby(data, keyfunc):
                g_names = set([f.name for f in group])
                fields_expressions = []
                for e in atomic_expr_field:
                    fs = e.atoms(ScalarField)
                    f_names = set([f.name for f in fs])
                    if f_names & g_names:
                        fields_expressions += [e]
                        space = list(fs)[0].space

                eval_field = EvalArrayField(space, fields_expressions,
                                            mapping=mapping,backend=self.backend)

                self._eval_fields.append(eval_field)
                for k,v in eval_field.map_stmts.items():
                    self._map_stmts_fields[k] = v

        # update dependencies
        self._dependencies += self.eval_fields
        # ...

        # ... TODO add it as a method to basic class
        nderiv = 1
        if isinstance(expr, Matrix):
            n_rows, n_cols = expr.shape
            for i_row in range(0, n_rows):
                for i_col in range(0, n_cols):
                    d = get_max_partial_derivatives(expr[i_row,i_col])
                    nderiv = max(nderiv, max(d.values()))
        else:
            d = get_max_partial_derivatives(expr)
            nderiv = max(nderiv, max(d.values()))

        self._max_nderiv = nderiv
        # ...

        # ... mapping
        mapping = self.mapping
        self._eval_mapping = None
        if mapping:

            space = self.spaces[0]

            eval_mapping = EvalArrayMapping(space, mapping,
                                            nderiv=nderiv,
                                            is_rational_mapping=self.is_rational_mapping,
                                            backend=self.backend)
            self._eval_mapping = eval_mapping

            # update dependencies
            self._dependencies += [self.eval_mapping]
        # ...

        # ... declarations
        fields        = symbols(fields_str)
        fields_logical = symbols(fields_logical_str)

        fields_coeffs = variables(['coeff_{}'.format(f) for f in field_atoms],
                                          dtype='real', rank=dim, cls=IndexedVariable)
        fields_val    = variables(['{}_values'.format(f) for f in fields_str],
                                          dtype='real', rank=dim, cls=IndexedVariable)

        fields_tmp_coeffs = variables(['tmp_coeff_{}'.format(f) for f in field_atoms],
                                              dtype='real', rank=dim, cls=IndexedVariable)

#        vector_fields        = symbols(vector_fields_str)
#        vector_fields_logical = symbols(vector_fields_logical_str)
#
#        vector_field_atoms = [f[i] for f in vector_field_atoms for i in range(0, dim)]
#        coeffs = ['coeff_{}'.format(print_expression(f)) for f in vector_field_atoms]
#        vector_fields_coeffs = variables(coeffs, dtype='real', rank=dim, cls=IndexedVariable)
#
#        vector_fields_val    = variables(['{}_values'.format(f) for f in vector_fields_str],
#                                          dtype='real', rank=dim, cls=IndexedVariable)
        # ...

        # ...
        mapping_elements = ()
        mapping_coeffs = ()
        mapping_values = ()
        if mapping:
            _eval = self.eval_mapping
            _print = lambda i: print_expression(i, mapping_name=False)

            mapping_elements = [_print(i) for i in _eval.elements]
            mapping_elements = symbols(tuple(mapping_elements))

            mapping_coeffs = [_print(i) for i in _eval.mapping_coeffs]
            mapping_coeffs = variables(mapping_coeffs, dtype='real', rank=dim, cls=IndexedVariable)

            mapping_values = [_print(i) for i in _eval.mapping_values]
            mapping_values = variables(mapping_values, dtype='real', rank=dim, cls=IndexedVariable)
        # ...

#        # ...
#        self._fields_val = fields_val
#        self._vector_fields_val = vector_fields_val
#        self._fields = fields
#        self._fields_logical = fields_logical
#        self._fields_coeffs = fields_coeffs
#        self._fields_tmp_coeffs = fields_tmp_coeffs
#        self._vector_fields = vector_fields
#        self._vector_fields_logical = vector_fields_logical
#        self._vector_fields_coeffs = vector_fields_coeffs
#        self._mapping_coeffs = mapping_coeffs
#        # ...

        # ...
        for l,arr_ti in zip(lengths, arr_tis):
            prelude += [Assign(l, Len(arr_ti))]
        # ...

        # ...
        slices = [Slice(None,None)]*dim
        for i_row in range(0, n_rows):
            for i_col in range(0, n_cols):
                symbol = d_symbols[i_row,i_col]
                prelude += [Assign(symbol[slices], 0.)]
        # ...

        # ... fields
        for i in range(len(fields_val)):
            body.append(Assign(fields[i],fields_val[i][indices]))
        # ...

        # ... mapping
        if mapping:
            for value, array in zip(mapping_elements, mapping_values):
                body.append(Assign(value, array[indices]))

            jac = mapping.det_jacobian
            jac = SymbolicExpr(jac)

            det_jac = SymbolicExpr(SymbolicDeterminant(mapping))

            body += [Assign(det_jac, jac)]

            body += [Print(mapping_elements)]
            print(mapping_elements)
        # ...

        # ...
        for i_row in range(0, n_rows):
            for i_col in range(0, n_cols):
                symbol = d_symbols[i_row,i_col]
                symbol = symbol[indices]

                if isinstance(expr, (Matrix, ImmutableDenseMatrix)):
                    body += [Assign(symbol, expr[i_row,i_col])]

                else:
                    body += [Assign(symbol, expr)]

        for i in range(dim-1,-1,-1):
            x = indices[i]
            rx = ranges[i]

            ti = tis[i]
            arr_ti = arr_tis[i]
            body = [Assign(ti, arr_ti[x])] + body
            if self.with_coordinates:
                xi = xis[i]
                arr_xi = arr_xis[i]
                body = [Assign(xi, arr_xi[x])] + body

            body = [For(x, rx, body)]
        # ...

        # call eval field
        for eval_field in self.eval_fields:
            args = degrees + spans + basis + fields_coeffs + fields_val
            args = eval_field.build_arguments(args)
            body = [FunctionCall(eval_field.func, args)] + body

#        # call eval vector_field
#        for eval_vector_field in self.eval_vector_fields:
#            args = degrees + basis + vector_fields_coeffs + vector_fields_val
#            args = eval_vector_field.build_arguments(args)
#            body = [FunctionCall(eval_vector_field.func, args)] + body

        # call eval mapping
        if self.eval_mapping:
            args = (degrees + spans + basis + mapping_coeffs + mapping_values)
            args = eval_mapping.build_arguments(args)
            body = [FunctionCall(eval_mapping.func, args)] + body


        if fields:
            imports += [Import('zeros', 'numpy')]
            for F_value in fields_val:
                prelude += [Assign(F_value, Zeros(lengths))]

#        if vector_fields_val:
#            for F_value in vector_fields_val:
#                prelude += [Assign(F_value, Zeros(lengths))]

        if mapping:
            imports += [Import('zeros', 'numpy')]
            for M_value in mapping_values:
                prelude += [Assign(M_value, Zeros(lengths))]

        # ...
        body = prelude + body
        # ...

        # ... get math functions and constants
        math_elements = math_atoms_as_str(expr)
        math_imports = []
        for e in math_elements:
            math_imports += [Import(e, 'numpy')]

        imports += math_imports
        # ...

        # ...
        self._basic_args = [*arr_tis]
        self._basic_args = tuple(self._basic_args)
        # ...

        # ...
        mats = []
        for i in range(0, n_rows):
            for j in range(0, n_cols):
                mats.append(d_symbols[i,j])
        mats = tuple(mats)
        self._global_mats = mats
        # ...

        # ...
        mats_types = []
        if isinstance(expr, (Matrix, ImmutableDenseMatrix)):
            for i in range(0, n_rows):
                for j in range(0, n_cols):
                    dtype = 'float'
                    if expr[i,j].atoms(ImaginaryUnit):
                        dtype = 'complex'
                    mats_types.append(dtype)

        else:
            dtype = 'float'
            if expr.atoms(ImaginaryUnit):
                dtype = 'complex'
            mats_types.append(dtype)

        mats_types = tuple(mats_types)
        self._global_mats_types = mats_types
        # ...

        self._imports = imports

        # function args
        args = ()
        if fields or mapping:
            args = degrees + spans + basis
        args = self.coordinates + args + fields_coeffs + mapping_coeffs + mats
        func_args = self.build_arguments(args)

#        func_args = self.build_arguments(self.coordinates + fields_coeffs + vector_fields_coeffs + mapping_coeffs + mats)

        decorators = {}
        header = None
        if self.backend['name'] == 'pyccel':
            decorators = {'types': build_types_decorator(func_args)}
        elif self.backend['name'] == 'numba':
            decorators = {'jit':[]}
        elif self.backend['name'] == 'pythran':
            header = build_pythran_types_header(self.name, func_args)

        return FunctionDef(self.name, list(func_args), [], body,
                           decorators=decorators,header=header)


class GltInterface(SplBasic):

    def __new__(cls, kernel, name=None, mapping=None, is_rational_mapping=None, backend=None):

        if not isinstance(kernel, GltKernel):
            raise TypeError('> Expecting an GltKernel')

        obj = SplBasic.__new__(cls, kernel.tag, name=name,
                               prefix='interface', mapping=mapping,
                               is_rational_mapping=is_rational_mapping)

        obj._kernel = kernel
        obj._mapping = mapping
        obj._backend = backend

        # update dependencies
        obj._dependencies += [kernel]

        obj._func = obj._initialize()
        return obj

    @property
    def kernel(self):
        return self._kernel

    @property
    def mapping(self):
        return self._mapping

    @property
    def backend(self):
        return self._backend

    # needed for MPI comm => TODO improve BasicCodeGen
    @property
    def max_nderiv(self):
        return None

    def build_arguments(self, data):
        # data must be at the end, since they are optional
        return self.basic_args + data

    @property
    def in_arguments(self):
        return self._in_arguments

    @property
    def inout_arguments(self):
        return self._inout_arguments

    @property
    def coordinates(self):
        return self.kernel.coordinates

    @property
    def user_functions(self):
        return self.kernel.user_functions

    def _initialize(self):
        form = self.kernel.form
        kernel = self.kernel
        global_mats = kernel.global_mats
        global_mats_types = kernel.global_mats_types
        fields = form.fields
        fields = sorted(fields, key=lambda x: str(x.name))
        fields = tuple(fields)

        dim = form.ldim

        mapping = ()
        if self.mapping: mapping = Symbol('mapping')

        # ... declarations
        test_space = Symbol('W')
        trial_space = Symbol('V')

        arr_tis    = symbols('arr_t1:%d'%(dim+1), cls=IndexedBase)
        lengths    = symbols('k1:%d'%(dim+1))
        degrees    = variables( 'p1:%s'%(dim+1), 'int')

        if fields or mapping:
            basis_values = Symbol('basis_values')

            basis  = variables( 'basis_1:%s'%(dim+1),
                                dtype = 'real',
                                rank = 4,
                                cls = IndexedVariable )

            spans  = variables( 'spans_1:%s'%(dim+1),
                                dtype = 'int',
                                rank = 1,
                                cls = IndexedVariable )
        # ...

        # ...
        if mapping or fields:
            self._basic_args = kernel.basic_args + (test_space, basis_values,)

        else:
            self._basic_args = kernel.basic_args + (test_space, )
        # ...

        # ...
        imports = []
        prelude = []
        body = []
        # ...

        # ...
        body += [Assign(degrees, DottedName(test_space, 'degree'))]
        # ...

        # ...
        grid_data = ()
        if mapping or fields:
            body += [Assign(spans, DottedName(basis_values, 'spans'))]
            body += [Assign(basis, DottedName(basis_values, 'basis'))]

            grid_data = (*degrees, *spans, *basis)
        # ...

        # ...
        if mapping:
            for i, coeff in enumerate(kernel.mapping_coeffs):
                component = IndexedBase(DottedName(mapping, '_fields'))[i]
                body += [Assign(coeff, DottedName(component, '_coeffs', '_data'))]
        # ...

        # ...
        imports += [Import('zeros', 'numpy')]
        # ...

        # ...
        for l,arr_ti in zip(lengths, arr_tis):
            prelude += [Assign(l, Len(arr_ti))]
        # ...

        # ...
        if dim > 1:
            lengths = Tuple(*lengths)
            lengths = [lengths]

        for M,dtype in zip(global_mats, global_mats_types):
            if_cond = Is(M, Nil())

            _args = list(lengths) + ['dtype={}'.format(dtype)]
            if_body = [Assign(M, FunctionCall('zeros', _args))]

            stmt = If((if_cond, if_body))
            body += [stmt]
        # ...

        # ...
        body = prelude + body
        # ...

        # ...
        self._inout_arguments = list(global_mats)
        self._in_arguments = list(self.coordinates) + list(self.kernel.constants) + list(fields)
        # ...

        # ... call to kernel
        # TODO add fields
        mat_data       = tuple(global_mats)

        field_data     = [DottedName(F, '_coeffs', '_data') for F in fields]
        field_data     = tuple(field_data)

        args = ()
        if fields or mapping:
            args = degrees + spans + basis
        args = self.coordinates + args + field_data + kernel.mapping_coeffs + mat_data
        args = kernel.build_arguments(args)

        body += [FunctionCall(kernel.func, args)]
        # ...

        # ... results
        if len(global_mats) == 1:
            M = global_mats[0]
            body += [Return(M)]

        else:
            body += [Return(global_mats)]
        # ...

        # ... arguments
        mats = [Assign(M, Nil()) for M in global_mats]
        mats = tuple(mats)

        if mapping:
            mapping = (mapping,)

        # TODO improve using in_arguments
        if self.kernel.constants:
            constants = self.kernel.constants

            if self.coordinates:
                coordinates = self.coordinates
                args = mapping + constants + coordinates + fields + mats

            else:
                args = mapping + constants + fields + mats

        else:
            if self.coordinates:
                coordinates = self.coordinates
                args = mapping + coordinates + fields + mats

            else:
                args = mapping + fields + mats

        func_args = self.build_arguments(args)
        # ...

        self._imports = imports
        return FunctionDef(self.name, list(func_args), [], body)
