# pyflakes.py - Python code linting
# This specific module is a derivative of PyFlakes and part of the SublimeLint project.
# SublimeLint is (c) 2012 Ryan Hileman and licensed under the MIT license.
# URL: https://github.com/lunixbochs/sublimelint
#
# The original copyright notices for this file/project follows:
#
# (c) 2005-2008 Divmod, Inc.
# See LICENSE file for details
#
# The LICENSE file is as follows:
#
# Copyright (c) 2005 Divmod, Inc., http://www.divmod.com/
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import sys

import __builtin__
import os.path
import compiler
from compiler import ast

class messages:
	class Message(object):
		message = ''
		message_args = ()
		def __init__(self, filename, lineno):
			self.filename = filename
			self.lineno = lineno
		def __str__(self):
			return self.message % self.message_args


	class UnusedImport(Message):
		message = '%r imported but unused'
		def __init__(self, filename, lineno, name):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.message_args = (name,)


	class RedefinedWhileUnused(Message):
		message = 'redefinition of unused %r from line %r'
		def __init__(self, filename, lineno, name, orig_lineno):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.orig_lineno = orig_lineno
			self.message_args = (name, orig_lineno)


	class ImportShadowedByLoopVar(Message):
		message = 'import %r from line %r shadowed by loop variable'
		def __init__(self, filename, lineno, name, orig_lineno):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.orig_lineno = orig_lineno
			self.message_args = (name, orig_lineno)


	class ImportStarUsed(Message):
		message = "'from %s import *' used; unable to detect undefined names"
		def __init__(self, filename, lineno, modname):
			messages.Message.__init__(self, filename, lineno)
			self.modname = modname
			self.message_args = (modname,)


	class UndefinedName(Message):
		message = 'undefined name %r'
		def __init__(self, filename, lineno, name):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.message_args = (name,)



	class UndefinedExport(Message):
		message = 'undefined name %r in __all__'
		def __init__(self, filename, lineno, name):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.message_args = (name,)



	class UndefinedLocal(Message):
		message = "local variable %r (defined in enclosing scope on line %r) referenced before assignment"
		def __init__(self, filename, lineno, name, orig_lineno):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.orig_lineno = orig_lineno
			self.message_args = (name, orig_lineno)


	class DuplicateArgument(Message):
		message = 'duplicate argument %r in function definition'
		def __init__(self, filename, lineno, name):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.message_args = (name,)


	class RedefinedFunction(Message):
		message = 'redefinition of function %r from line %r'
		def __init__(self, filename, lineno, name, orig_lineno):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.orig_lineno = orig_lineno
			self.message_args = (name, orig_lineno)


	class LateFutureImport(Message):
		message = 'future import(s) %r after other statements'
		def __init__(self, filename, lineno, names):
			messages.Message.__init__(self, filename, lineno)
			self.names = names
			self.message_args = (names,)


	class UnusedVariable(Message):
		"""
		Indicates that a variable has been explicity assigned to but not actually
		used.
		"""

		message = 'local variable %r is assigned to but never used'
		def __init__(self, filename, lineno, name):
			messages.Message.__init__(self, filename, lineno)
			self.name = name
			self.message_args = (name,)

class Binding(object):
	"""
	Represents the binding of a value to a name.

	The checker uses this to keep track of which names have been bound and
	which names have not. See L{Assignment} for a special type of binding that
	is checked with stricter rules.

	@ivar used: pair of (L{Scope}, line-number) indicating the scope and
				line number that this binding was last used
	"""

	def __init__(self, name, source):
		self.name = name
		self.source = source
		self.used = False


	def __str__(self):
		return self.name


	def __repr__(self):
		return '<%s object %r from line %r at 0x%x>' % (self.__class__.__name__,
														self.name,
														self.source.lineno,
														id(self))

class UnBinding(Binding):
	'''Created by the 'del' operator.'''



class Importation(Binding):
	"""
	A binding created by an import statement.

	@ivar fullName: The complete name given to the import statement,
		possibly including multiple dotted components.
	@type fullName: C{str}
	"""
	def __init__(self, name, source):
		self.fullName = name
		name = name.split('.')[0]
		super(Importation, self).__init__(name, source)



class Argument(Binding):
	"""
	Represents binding a name as an argument.
	"""



class Assignment(Binding):
	"""
	Represents binding a name with an explicit assignment.

	The checker will raise warnings for any Assignment that isn't used. Also,
	the checker does not consider assignments in tuple/list unpacking to be
	Assignments, rather it treats them as simple Bindings.
	"""



class FunctionDefinition(Binding):
	pass



class ExportBinding(Binding):
	"""
	A binding created by an C{__all__} assignment.  If the names in the list
	can be determined statically, they will be treated as names for export and
	additional checking applied to them.

	The only C{__all__} assignment that can be recognized is one which takes
	the value of a literal list containing literal strings.  For example::

		__all__ = ["foo", "bar"]

	Names which are imported and not otherwise used but appear in the value of
	C{__all__} will not have an unused import warning reported for them.
	"""
	def names(self):
		"""
		Return a list of the names referenced by this binding.
		"""
		names = []
		if isinstance(self.source, ast.List):
			for node in self.source.nodes:
				if isinstance(node, ast.Const):
					names.append(node.value)
		return names



class Scope(dict):
	importStarred = False       # set to True when import * is found


	def __repr__(self):
		return '<%s at 0x%x %s>' % (self.__class__.__name__, id(self), dict.__repr__(self))


	def __init__(self):
		super(Scope, self).__init__()



class ClassScope(Scope):
	pass



class FunctionScope(Scope):
	"""
	I represent a name scope for a function.

	@ivar globals: Names declared 'global' in this function.
	"""
	def __init__(self):
		super(FunctionScope, self).__init__()
		self.globals = {}



class ModuleScope(Scope):
	pass


# Globally defined names which are not attributes of the __builtin__ module.
_MAGIC_GLOBALS = ['__file__', '__builtins__']



class Checker(object):
	"""
	I check the cleanliness and sanity of Python code.

	@ivar _deferredFunctions: Tracking list used by L{deferFunction}.  Elements
		of the list are two-tuples.  The first element is the callable passed
		to L{deferFunction}.  The second element is a copy of the scope stack
		at the time L{deferFunction} was called.

	@ivar _deferredAssignments: Similar to C{_deferredFunctions}, but for
		callables which are deferred assignment checks.
	"""

	nodeDepth = 0
	traceTree = False

	def __init__(self, tree, filename='(none)'):
		self._deferredFunctions = []
		self._deferredAssignments = []
		self.dead_scopes = []
		self.messages = []
		self.filename = filename
		self.scopeStack = [ModuleScope()]
		self.futuresAllowed = True
		self.handleChildren(tree)
		self._runDeferred(self._deferredFunctions)
		# Set _deferredFunctions to None so that deferFunction will fail
		# noisily if called after we've run through the deferred functions.
		self._deferredFunctions = None
		self._runDeferred(self._deferredAssignments)
		# Set _deferredAssignments to None so that deferAssignment will fail
		# noisly if called after we've run through the deferred assignments.
		self._deferredAssignments = None
		del self.scopeStack[1:]
		self.popScope()
		self.check_dead_scopes()


	def deferFunction(self, callable):
		'''
		Schedule a function handler to be called just before completion.

		This is used for handling function bodies, which must be deferred
		because code later in the file might modify the global scope. When
		`callable` is called, the scope at the time this is called will be
		restored, however it will contain any new bindings added to it.
		'''
		self._deferredFunctions.append((callable, self.scopeStack[:]))


	def deferAssignment(self, callable):
		"""
		Schedule an assignment handler to be called just after deferred
		function handlers.
		"""
		self._deferredAssignments.append((callable, self.scopeStack[:]))


	def _runDeferred(self, deferred):
		"""
		Run the callables in C{deferred} using their associated scope stack.
		"""
		for handler, scope in deferred:
			self.scopeStack = scope
			handler()


	def scope(self):
		return self.scopeStack[-1]
	scope = property(scope)

	def popScope(self):
		self.dead_scopes.append(self.scopeStack.pop())


	def check_dead_scopes(self):
		"""
		Look at scopes which have been fully examined and report names in them
		which were imported but unused.
		"""
		for scope in self.dead_scopes:
			export = isinstance(scope.get('__all__'), ExportBinding)
			if export:
				all = scope['__all__'].names()
				if os.path.split(self.filename)[1] != '__init__.py':
					# Look for possible mistakes in the export list
					undefined = set(all) - set(scope)
					for name in undefined:
						self.report(
							messages.UndefinedExport,
							scope['__all__'].source.lineno,
							name)
			else:
				all = []

			# Look for imported names that aren't used.
			for importation in scope.itervalues():
				if isinstance(importation, Importation):
					if not importation.used and importation.name not in all:
						self.report(
							messages.UnusedImport,
							importation.source.lineno,
							importation.name)


	def pushFunctionScope(self):
		self.scopeStack.append(FunctionScope())

	def pushClassScope(self):
		self.scopeStack.append(ClassScope())

	def report(self, messageClass, *args, **kwargs):
		self.messages.append(messageClass(self.filename, *args, **kwargs))

	def handleChildren(self, tree):
		for node in tree.getChildNodes():
			self.handleNode(node, tree)

	def handleNode(self, node, parent):
		node.parent = parent
		if self.traceTree:
			print '  ' * self.nodeDepth + node.__class__.__name__
		self.nodeDepth += 1
		nodeType = node.__class__.__name__.upper()
		if nodeType not in ('STMT', 'FROM'):
			self.futuresAllowed = False
		try:
			handler = getattr(self, nodeType)
			handler(node)
		finally:
			self.nodeDepth -= 1
		if self.traceTree:
			print '  ' * self.nodeDepth + 'end ' + node.__class__.__name__

	def ignore(self, node):
		pass

	STMT = PRINT = PRINTNL = TUPLE = LIST = ASSTUPLE = ASSATTR = \
	ASSLIST = GETATTR = SLICE = SLICEOBJ = IF = CALLFUNC = DISCARD = \
	RETURN = ADD = MOD = SUB = NOT = UNARYSUB = INVERT = ASSERT = COMPARE = \
	SUBSCRIPT = AND = OR = TRYEXCEPT = RAISE = YIELD = DICT = LEFTSHIFT = \
	RIGHTSHIFT = KEYWORD = TRYFINALLY = WHILE = EXEC = MUL = DIV = POWER = \
	FLOORDIV = BITAND = BITOR = BITXOR = LISTCOMPFOR = LISTCOMPIF = \
	AUGASSIGN = BACKQUOTE = UNARYADD = GENEXPR = GENEXPRFOR = GENEXPRIF = \
	IFEXP = handleChildren

	CONST = PASS = CONTINUE = BREAK = ELLIPSIS = ignore

	def addBinding(self, lineno, value, reportRedef=True):
		'''Called when a binding is altered.

		- `lineno` is the line of the statement responsible for the change
		- `value` is the optional new value, a Binding instance, associated
		  with the binding; if None, the binding is deleted if it exists.
		- if `reportRedef` is True (default), rebinding while unused will be
		  reported.
		'''
		if (isinstance(self.scope.get(value.name), FunctionDefinition)
					and isinstance(value, FunctionDefinition)):
			self.report(messages.RedefinedFunction,
						lineno, value.name, self.scope[value.name].source.lineno)

		if not isinstance(self.scope, ClassScope):
			for scope in self.scopeStack[::-1]:
				existing = scope.get(value.name)
				if (isinstance(existing, Importation)
						and not existing.used
						and (not isinstance(value, Importation) or value.fullName == existing.fullName)
						and reportRedef):

					self.report(messages.RedefinedWhileUnused,
								lineno, value.name, scope[value.name].source.lineno)

		if isinstance(value, UnBinding):
			try:
				del self.scope[value.name]
			except KeyError:
				self.report(messages.UndefinedName, lineno, value.name)
		else:
			self.scope[value.name] = value


	def WITH(self, node):
		"""
		Handle C{with} by checking the target of the statement (which can be an
		identifier, a list or tuple of targets, an attribute, etc) for
		undefined names and defining any it adds to the scope and by continuing
		to process the suite within the statement.
		"""
		# Check the "foo" part of a "with foo as bar" statement.  Do this no
		# matter what, since there's always a "foo" part.
		self.handleNode(node.expr, node)

		if node.vars is not None:
			self.handleNode(node.vars, node)

		self.handleChildren(node.body)


	def GLOBAL(self, node):
		"""
		Keep track of globals declarations.
		"""
		if isinstance(self.scope, FunctionScope):
			self.scope.globals.update(dict.fromkeys(node.names))

	def LISTCOMP(self, node):
		for qual in node.quals:
			self.handleNode(qual, node)
		self.handleNode(node.expr, node)

	GENEXPRINNER = LISTCOMP

	def FOR(self, node):
		"""
		Process bindings for loop variables.
		"""
		vars = []
		def collectLoopVars(n):
			if hasattr(n, 'name'):
				vars.append(n.name)
			else:
				for c in n.getChildNodes():
					collectLoopVars(c)

		collectLoopVars(node.assign)
		for varn in vars:
			if (isinstance(self.scope.get(varn), Importation)
					# unused ones will get an unused import warning
					and self.scope[varn].used):
				self.report(messages.ImportShadowedByLoopVar,
							node.lineno, varn, self.scope[varn].source.lineno)

		self.handleChildren(node)

	def NAME(self, node):
		"""
		Locate the name in locals / function / globals scopes.
		"""
		# try local scope
		importStarred = self.scope.importStarred
		try:
			self.scope[node.name].used = (self.scope, node.lineno)
		except KeyError:
			pass
		else:
			return

		# try enclosing function scopes

		for scope in self.scopeStack[-2:0:-1]:
			importStarred = importStarred or scope.importStarred
			if not isinstance(scope, FunctionScope):
				continue
			try:
				scope[node.name].used = (self.scope, node.lineno)
			except KeyError:
				pass
			else:
				return

		# try global scope

		importStarred = importStarred or self.scopeStack[0].importStarred
		try:
			self.scopeStack[0][node.name].used = (self.scope, node.lineno)
		except KeyError:
			if ((not hasattr(__builtin__, node.name))
					and node.name not in _MAGIC_GLOBALS
					and not importStarred):
				if (os.path.basename(self.filename) == '__init__.py' and
					node.name == '__path__'):
					# the special name __path__ is valid only in packages
					pass
				else:
					self.report(messages.UndefinedName, node.lineno, node.name)


	def FUNCTION(self, node):
		if getattr(node, "decorators", None) is not None:
			self.handleChildren(node.decorators)
		self.addBinding(node.lineno, FunctionDefinition(node.name, node))
		self.LAMBDA(node)

	def LAMBDA(self, node):
		for default in node.defaults:
			self.handleNode(default, node)

		def runFunction():
			args = []

			def addArgs(arglist):
				for arg in arglist:
					if isinstance(arg, tuple):
						addArgs(arg)
					else:
						if arg in args:
							self.report(messages.DuplicateArgument, node.lineno, arg)
						args.append(arg)

			self.pushFunctionScope()
			addArgs(node.argnames)
			for name in args:
				self.addBinding(node.lineno, Argument(name, node), reportRedef=False)
			self.handleNode(node.code, node)
			def checkUnusedAssignments():
				"""
				Check to see if any assignments have not been used.
				"""
				for name, binding in self.scope.iteritems():
					if (not binding.used and not name in self.scope.globals
						and isinstance(binding, Assignment)):
						self.report(messages.UnusedVariable,
									binding.source.lineno, name)
			self.deferAssignment(checkUnusedAssignments)
			self.popScope()

		self.deferFunction(runFunction)


	def CLASS(self, node):
		"""
		Check names used in a class definition, including its decorators, base
		classes, and the body of its definition.  Additionally, add its name to
		the current scope.
		"""
		if getattr(node, "decorators", None) is not None:
			self.handleChildren(node.decorators)
		for baseNode in node.bases:
			self.handleNode(baseNode, node)
		self.addBinding(node.lineno, Binding(node.name, node))
		self.pushClassScope()
		self.handleChildren(node.code)
		self.popScope()


	def ASSNAME(self, node):
		if node.flags == 'OP_DELETE':
			if isinstance(self.scope, FunctionScope) and node.name in self.scope.globals:
				del self.scope.globals[node.name]
			else:
				self.addBinding(node.lineno, UnBinding(node.name, node))
		else:
			# if the name hasn't already been defined in the current scope
			if isinstance(self.scope, FunctionScope) and node.name not in self.scope:
				# for each function or module scope above us
				for scope in self.scopeStack[:-1]:
					if not isinstance(scope, (FunctionScope, ModuleScope)):
						continue
					# if the name was defined in that scope, and the name has
					# been accessed already in the current scope, and hasn't
					# been declared global
					if (node.name in scope
							and scope[node.name].used
							and scope[node.name].used[0] is self.scope
							and node.name not in self.scope.globals):
						# then it's probably a mistake
						self.report(messages.UndefinedLocal,
									scope[node.name].used[1],
									node.name,
									scope[node.name].source.lineno)
						break

			if isinstance(node.parent,
						  (ast.For, ast.ListCompFor, ast.GenExprFor,
						   ast.AssTuple, ast.AssList)):
				binding = Binding(node.name, node)
			elif (node.name == '__all__' and
				  isinstance(self.scope, ModuleScope) and
				  isinstance(node.parent, ast.Assign)):
				binding = ExportBinding(node.name, node.parent.expr)
			else:
				binding = Assignment(node.name, node)
			if node.name in self.scope:
				binding.used = self.scope[node.name].used
			self.addBinding(node.lineno, binding)

	def ASSIGN(self, node):
		self.handleNode(node.expr, node)
		for subnode in node.nodes[::-1]:
			self.handleNode(subnode, node)

	def IMPORT(self, node):
		for name, alias in node.names:
			name = alias or name
			importation = Importation(name, node)
			self.addBinding(node.lineno, importation)

	def FROM(self, node):
		if node.modname == '__future__':
			if not self.futuresAllowed:
				self.report(messages.LateFutureImport, node.lineno, [n[0] for n in node.names])
		else:
			self.futuresAllowed = False

		for name, alias in node.names:
			if name == '*':
				self.scope.importStarred = True
				self.report(messages.ImportStarUsed, node.lineno, node.modname)
				continue
			name = alias or name
			importation = Importation(name, node)
			if node.modname == '__future__':
				importation.used = (self.scope, node.lineno)
			self.addBinding(node.lineno, importation)

class OffsetError(messages.Message):
	message = '%r at offset %r'
	def __init__(self, filename, lineno, text, offset):
		messages.Message.__init__(self, filename, lineno)
		self.offset = offset
		self.message_args = (text, offset)

class PythonError(messages.Message):
	message = '%r'
	def __init__(self, filename, lineno, text):
		messages.Message.__init__(self, filename, lineno)
		self.message_args = (text,)

def check(codeString, filename):
	codeString = codeString.rstrip()
	try:
		try:
			compile(codeString, filename, "exec")
		except MemoryError:
			# Python 2.4 will raise MemoryError if the source can't be
			# decoded.
			if sys.version_info[:2] == (2, 4):
				raise SyntaxError(None)
			raise
	except (SyntaxError, IndentationError), value:
		# print traceback.format_exc() # helps debug new cases
		msg = value.args[0]

		lineno, offset, text = value.lineno, value.offset, value.text

		# If there's an encoding problem with the file, the text is None.
		if text is None:
			# Avoid using msg, since for the only known case, it contains a
			# bogus message that claims the encoding the file declared was
			# unknown.
			if msg.startswith('duplicate argument'):
				arg = msg.split('duplicate argument ',1)[1].split(' ',1)[0].strip('\'"')
				error = messages.DuplicateArgument(filename, lineno, arg)
			else:
				error = PythonError(filename, lineno, msg)
		else:
			line = text.splitlines()[-1]

			if offset is not None:
				offset = offset - (len(text) - len(line))

			if offset is not None:
				error = OffsetError(filename, lineno, msg, offset)
			else:
				error = PythonError(filename, lineno, msg)

		return [error]
	except ValueError, e:
		return [PythonError(filename, 0, e.args[0])]
	else:
		# Okay, it's syntactically valid.  Now parse it into an ast and check
		# it.
		tree = compiler.parse(codeString)
		w = Checker(tree, filename)
		w.messages.sort(lambda a, b: cmp(a.lineno, b.lineno))
		return w.messages

# end pyflakes