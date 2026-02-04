# Security Documentation

This document outlines security considerations, threat models, and best practices for Parqcel.

## Executive Summary

Parqcel is a desktop application for data analysis with an optional AI assistant feature. The primary security concern is the **execution of LLM-generated Python code** to transform data. While comprehensive validation is in place, users should understand the risks and limitations.

**Risk Level**: Medium (when AI features are enabled)  
**Mitigation**: AST-based code validation, restricted execution environment, user review workflow

## Threat Model

### Assets
1. **User Data**: Parquet/CSV/Excel files containing potentially sensitive information
2. **System Resources**: CPU, memory, filesystem access
3. **API Keys**: OpenAI/HuggingFace credentials (stored in OS keyring)

### Threat Actors
1. **Malicious LLM Output**: AI backend returns malicious code designed to exploit the application
2. **Compromised Dependencies**: Third-party libraries with known vulnerabilities
3. **User Error**: Accidental execution of dangerous operations on sensitive data

### Attack Vectors

#### 1. Code Injection via LLM (Primary Risk)
**Description**: AI assistant generates code that escapes validation and executes arbitrary operations.

**Example Attacks**:
- Accessing system variables via dunder attributes
- Importing modules to execute system commands
- Reading/writing arbitrary files
- Network operations

**Mitigation**:
- AST-based validation (see `ai/validator.py`)
- Whitelist approach: only `df` and `pl` operations allowed
- No import statements, lambdas, or comprehensions
- Dunder attribute access blocked

**Limitations**:
- AST validation is not a complete sandbox
- Does not protect against resource exhaustion (infinite loops, memory bombs)
- New Python features may bypass validation
- Validation logic itself may have bugs

#### 2. Dependency Vulnerabilities
**Description**: Known CVEs in dependencies (PyQt6, Polars, numpy, scikit-learn, etc.)

**Mitigation**:
- Regular dependency updates
- Monitor security advisories
- Pin specific versions in production
- Use `gh-advisory-database` tool before adding dependencies

#### 3. API Key Exposure
**Description**: OpenAI/HuggingFace keys leaked via logs, config files, or error messages

**Mitigation**:
- Keys stored in OS keyring (not plaintext config)
- Logs mask credential values
- Environment variables not echoed in debug output

## Validation Details (`ai/validator.py`)

### Allowed Operations
The validator permits only these AST node types:
- Basic expressions: constants, tuples, lists, dicts, sets
- Comparisons and boolean operations
- Binary/unary arithmetic operations
- Attribute access/subscripting on `df` or `pl` only
- Function calls on `df` or `pl` chains only
- Variable assignments (temp variables allowed)

### Explicitly Blocked
- Import statements (any form)
- Lambda functions
- List/dict/set comprehensions, generator expressions
- Async/await syntax
- Dunder attributes (`__globals__`, `__dict__`, `__class__`, etc.)
- Direct function calls (e.g., `print()`, `open()`)
- Attribute access on unauthorized names

### Example: Safe vs. Unsafe Code

**Safe (Passes Validation)**:
```python
df.select(['col1', 'col2'])
df.filter(pl.col('age') > 18)
df.with_columns((pl.col('a') + pl.col('b')).alias('sum'))
result = df.sort('name')  # Temp variable allowed
```

**Unsafe (Blocked by Validator)**:
```python
import os; os.system('rm -rf /')  # Import blocked
df.__class__.__bases__  # Dunder attribute blocked
eval('malicious code')  # eval is not df/pl
print(df)  # Direct function call blocked
[x for x in df]  # Comprehension blocked
```

### Edge Cases and Limitations

#### Known Safe Bypasses: NONE CURRENTLY KNOWN
If you discover a validation bypass, please report it immediately.

#### Resource Exhaustion (NOT PROTECTED)
```python
# These pass validation but are dangerous:
df.join(df, how='cross')  # Cartesian product -> memory exhaustion
while True: pass  # Infinite loop
df.select([pl.col('x') ** 999999])  # CPU-intensive
```

**Recommendation**: 
- Set timeout for code execution (not currently implemented)
- Monitor resource usage during execution
- Only run AI suggestions on non-production data

## Secure Usage Guidelines

### For Users

1. **Treat AI Suggestions as Untrusted Input**
   - Always review generated code before executing
   - Understand what each operation does
   - Test on sample data first

2. **Data Classification**
   - Do NOT use AI features on:
     - Personally Identifiable Information (PII)
     - Financial records
     - Healthcare data (PHI)
     - Trade secrets
   - AI features send column names to external APIs

3. **API Key Management**
   - Use read-only API keys when possible
   - Rotate keys periodically
   - Monitor API usage for anomalies
   - Never share keys or commit to version control

4. **Network Security**
   - AI features require internet access
   - Data is NOT sent to AI providers (only column names and operations)
   - Use VPN in sensitive environments

### For Developers

1. **Before Adding Dependencies**
   ```bash
   # Check for known vulnerabilities
   python -m gh_advisory_database --ecosystem pip \
       --name package_name --version X.Y.Z
   ```

2. **Code Review Checklist**
   - [ ] No new `exec()` or `eval()` calls
   - [ ] No dynamic import statements
   - [ ] User input is validated
   - [ ] File operations use safe paths
   - [ ] API keys never logged

3. **Security Testing**
   ```bash
   # Run security-focused tests
   pytest tests/test_validator.py -v
   
   # Static analysis
   bandit -r src/
   
   # Check for common issues
   ruff check src/ --select S  # Security rules
   ```

## Incident Response

### If You Discover a Validation Bypass

1. **DO NOT** publicly disclose until patched
2. Report via private security advisory on GitHub
3. Include minimal reproduction code
4. Assess scope: local files? network access? system compromise?

### If API Keys Are Compromised

1. Immediately revoke keys in provider dashboard
2. Rotate to new keys
3. Audit recent API usage for suspicious activity
4. Check for unauthorized data access

## Security Roadmap

### Implemented ✅
- [x] AST-based code validation
- [x] Keyring-based credential storage
- [x] Comprehensive validation test suite
- [x] Security documentation

### Planned 📋
- [ ] Execution timeout for AI code (prevent infinite loops)
- [ ] Memory limits for operations
- [ ] Audit logging for AI executions
- [ ] Sandbox using subprocess isolation
- [ ] Rate limiting for AI API calls

### Under Consideration 🤔
- [ ] RestrictedPython integration (alternative validator)
- [ ] Process-based isolation (run AI code in separate process)
- [ ] Differential privacy for data statistics
- [ ] End-to-end encryption for API communication

## References

### Security Standards
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE-94: Code Injection](https://cwe.mitre.org/data/definitions/94.html)
- [CWE-502: Deserialization of Untrusted Data](https://cwe.mitre.org/data/definitions/502.html)

### Python Security
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [Bandit Security Linter](https://bandit.readthedocs.io/)

### Similar Projects
- [RestrictedPython](https://github.com/zopefoundation/RestrictedPython)
- [PyPy Sandboxing](https://doc.pypy.org/en/latest/sandbox.html)

## Contact

For security concerns or vulnerability reports:
- GitHub Security Advisories: [Create Advisory](https://github.com/SMcQueen2023/Parqcel/security/advisories)
- Email: See repository owner profile

---

**Last Updated**: 2026-02-04  
**Next Review**: Quarterly or after significant changes
