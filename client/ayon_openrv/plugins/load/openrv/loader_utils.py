"""Shared utilities for OpenRV loaders."""

import json
import rv
from ayon_core.pipeline.load import get_representation_path


def fetch_all_product_versions(project_name, product_id, logger):
    """Fetch all versions for a product using GraphQL.
    
    Args:
        project_name: AYON project name
        product_id: Product UUID
        logger: Logger instance for warnings
        
    Returns:
        List of version nodes sorted by version number (descending)
    """
    try:
        import os
        import requests
        
        url = os.environ.get("AYON_SERVER_URL", "").rstrip("/") + "/graphql"
        api_key = os.environ.get("AYON_API_KEY", "")
        
        if not url or not api_key:
            raise Exception("Missing AYON_SERVER_URL or AYON_API_KEY")

        query = """
        query GetProductVersions($projectName: String!, $productId: String!) {
          project(name: $projectName) {
            product(id: $productId) {
              versions {
                edges {
                  node {
                    id
                    version
                    status
                    author
                    taskId
                    createdAt
                    thumbnailId
                    representations {
                      edges {
                        node {
                          id
                          name
                          attrib {
                            path
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {"projectName": project_name, "productId": product_id}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        response = requests.post(
            url,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        versions = []
        edges = result.get('data', {}).get('project', {}).get('product', {}).get('versions', {}).get('edges', [])
        print(f"📊 [loader_utils] Found {len(edges)} version edges")
        
        for edge in edges:
            node = edge.get('node')
            if node:
                versions.append(node)
                print(f"  ✓ Version {node.get('version')}: {node.get('id')}")
        
        versions.sort(key=lambda v: v.get('version', 0), reverse=True)
        print(f"✅ [loader_utils] Returning {len(versions)} versions (sorted)")
        return versions
        
    except Exception as e:
        print(f"❌ [loader_utils] Error fetching versions: {e}")
        logger.warning(f"Could not fetch all product versions: {e}")
        import traceback
        traceback.print_exc()
        return []


def build_event_data_with_versions(context, filepath, logger):
    """Build event data with multi-version support.
    
    Args:
        context: Loader context dict
        filepath: Current file path
        logger: Logger instance
        
    Returns:
        Dict with event data including all versions
    """
    import json

    version_id = context['representation']['versionId']
    version_doc = context['version']
    project_name = context['project']['name']
    product_id = context['product']['id']
    product_name = context['product']['name']

    # Fetch all versions for this product
    all_product_versions = fetch_all_product_versions(project_name, product_id, logger)

    # Build versions list for dropdown
    versions = [f"v{v['version']:03d}" for v in all_product_versions] if all_product_versions else [f"v{version_doc.get('version', 1):03d}"]

    # Get current version representations
    representations = []
    try:
        from ayon_api import get_representations
        version_representations = get_representations(project_name, version_ids=[version_id])
        for rep in version_representations:
            representations.append({
                'id': rep['id'],
                'name': rep['name'],
                'path': rep.get('attrib', {}).get('path', '')
            })
        print(f"✅ [loader_utils] Got {len(representations)} representations")
    except Exception as e:
        print(f"⚠️ [loader_utils] Could not fetch representations: {e}")
        logger.debug(f"Could not fetch representations: {e}")
    
    # Build event data
    event_data = {
        'version_id': version_id,
        'task_id': version_doc['taskId'],
        'product_id': product_id,
        'product_name': product_name,
        'project_name': project_name,
        'path': context['folder']['path'],
        'current_version': f"v{version_doc.get('version', 1):03d}",
        'version_status': version_doc.get('status', 'N/A'),
        'author': version_doc.get('author', 'N/A'),
        'versions': versions,
        'all_product_versions': all_product_versions,
        'representations': representations,
        'current_representation_path': filepath
    }

    return event_data


def register_with_rv_operations(node, filepath, context, logger):
    """Store version metadata and fire RV event."""
    event_data = None
    try:
        event_data = build_event_data_with_versions(context, filepath, logger)
        event_data['node'] = node
        
        store_version_metadata(node, context, event_data)
        
        rv.commands.sendInternalEvent("ayon_source_loaded", json.dumps(event_data))
        logger.info(f"Fired ayon_source_loaded event with {len(event_data.get('all_product_versions', []))} versions")
    except Exception as e:
        store_version_metadata(node, context, None)
        logger.debug(f"Could not fire source loaded event: {e}")


def store_version_metadata(node, context, event_data=None):
    """Store version metadata in RV source node."""
    version = context.get("version", {})
    product = context.get("product", {})
    folder = context.get("folder", {})
    
    metadata = {
        'version_id': version.get("id"),
        'representation_id': context.get("representation", {}).get("id"),
        'file_path': get_representation_path(context["representation"]),
        'product_id': product.get("id"),
        'product_name': product.get("name"),
        'task_id': version.get("taskId"),
        'folder_path': folder.get("path"),
        'version_name': version.get("name"),
        'version_status': version.get("status"),
        'author': version.get("author"),
        'project_name': context.get("project", {}).get("name")
    }

    if event_data:
        metadata['versions'] = json.dumps(event_data.get('versions', []))
        metadata['all_product_versions'] = json.dumps(event_data.get('all_product_versions', []))
        metadata['representations'] = json.dumps(event_data.get('representations', []))

    for key, value in metadata.items():
        if value:
            prop = f"{node}.ayon.{key}"
            if not rv.commands.propertyExists(prop):
                rv.commands.newProperty(prop, rv.commands.StringType, 1)
            rv.commands.setStringProperty(prop, [value], True)
