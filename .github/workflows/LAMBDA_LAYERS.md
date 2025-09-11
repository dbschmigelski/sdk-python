# Lambda Layers Standard Operating Procedures (SOP)

## Overview

This document defines the standard operating procedures for managing Strands Agents Lambda layers across all AWS regions, Python versions, and architectures.

## Core Principles

### Version Synchronization
- **All variants must have the same layer version number** for each PyPI package version
- This includes all combinations of:
  - Python versions (3.10, 3.11, 3.12, 3.13)
  - Architectures (x86_64, aarch64)
  - AWS regions (all non opt-in regions)
- **Total: 136 individual Lambda layers** (17 regions × 2 architectures × 4 Python versions)
- Each layer is published separately but must maintain version synchronization

### Documentation Consistency
- Only **one row per PyPI version** appears in documentation
- The layer version number represents all variants for that PyPI package version

## Deployment Process

### Staging Region
- **us-east-1** serves as the staging region for all layer packages
- S3 bucket and layer zip files are created in us-east-1
- All other regions reference the same S3 objects from us-east-1

### 1. Initial Deployment
1. Run workflow with ALL options selected (default)
2. Specify PyPI package version
3. Type "Create Lambda Layer" to confirm
4. All 136 individual layers deploy in parallel (4 Python × 2 arch × 17 regions)
5. Each layer gets its own unique name: `strands-agents-py{VERSION}-{ARCH}`
6. Documentation automatically updates with new row

### 2. Version Buffering for New Variants
When adding new variants (new Python version, architecture, or region):

1. **Determine target layer version**: Check existing variants to find the highest layer version
2. **Buffer deployment**: Deploy new variants multiple times until layer version matches existing variants
3. **Example**: If existing variants are at layer version 5, deploy new variant 5 times to reach version 5

### 3. Handling Transient Failures
When some regions fail during deployment:

1. **Identify failed regions**: Check which combinations didn't complete successfully
2. **Targeted redeployment**: Use specific region/arch/Python inputs to redeploy failed combinations
3. **Version alignment**: Continue deploying until all variants reach the same layer version
4. **Verification**: Confirm all combinations have identical layer versions before updating docs

## Yank Process

### When to Yank
- Security vulnerabilities discovered in PyPI package
- Critical bugs affecting Lambda functionality
- Compliance requirements

### Yank Procedure
1. **Remove public permissions**:
   ```bash
   aws lambda remove-layer-version-permission \
     --layer-name strands-agents-py{VERSION}-{ARCH} \
     --version-number {LAYER_VERSION} \
     --statement-id public \
     --region {REGION}
   ```

2. **Update documentation**: Remove or mark the row as yanked in lambda-layers.md

3. **Coordinate across all variants**: Repeat for all 136 combinations

4. **Communication**: Notify users through appropriate channels

## Workflow Usage

### Full Deployment (Default)
- Python Version: ALL
- Architecture: ALL  
- Region: ALL
- Result: 136 parallel deployments

### Targeted Deployment
- Select specific values for failed/new variants
- Used for version synchronization and failure recovery

### Validation Steps
1. Verify all combinations completed successfully
2. Check layer versions are synchronized across all variants
3. Confirm documentation reflects single version per PyPI package
4. Test layer functionality in representative regions/architectures

## Troubleshooting

### Common Issues
- **Partial failures**: Use targeted deployment to retry failed combinations
- **Version drift**: Deploy additional times to align layer versions
- **Permission errors**: Verify IAM role has necessary permissions across all regions
- **S3 bucket issues**: Ensure buckets exist in all target regions

### Recovery Actions
1. Identify scope of issue (specific regions, architectures, Python versions)
2. Use targeted deployment to address specific failures
3. Continue until version synchronization is achieved
4. Update documentation only after full synchronization