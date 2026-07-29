package com.example.jaya.data.network

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.net.InetAddress

data class DiscoveredServer(
    val name: String,
    val host: InetAddress,
    val port: Int,
    val resolvedUrl: String
)

class NetworkDiscoveryManager(context: Context) {
    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val serviceType = "_jaya-server._tcp."

    private val _discoveredServers = MutableStateFlow<List<DiscoveredServer>>(emptyList())
    val discoveredServers: StateFlow<List<DiscoveredServer>> = _discoveredServers.asStateFlow()

    private val _isDiscovering = MutableStateFlow(false)
    val isDiscovering: StateFlow<Boolean> = _isDiscovering.asStateFlow()

    private val discoveryListener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(regType: String) {
            Log.d("NetworkDiscovery", "mDNS Service Discovery Started: $regType")
            _isDiscovering.value = true
        }

        override fun onServiceFound(service: NsdServiceInfo) {
            Log.d("NetworkDiscovery", "Compatible service discovered")
            if (service.serviceType == serviceType) {
                nsdManager.resolveService(service, resolveListener)
            }
        }

        override fun onServiceLost(service: NsdServiceInfo) {
            Log.d("NetworkDiscovery", "Compatible service lost")
            _discoveredServers.value = _discoveredServers.value.filter { it.name != service.serviceName }
        }

        override fun onDiscoveryStopped(serviceType: String) {
            Log.d("NetworkDiscovery", "Discovery stopped")
            _isDiscovering.value = false
        }

        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e("NetworkDiscovery", "Discovery start failed: Error $errorCode")
            _isDiscovering.value = false
            nsdManager.stopServiceDiscovery(this)
        }

        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e("NetworkDiscovery", "Discovery stop failed: Error $errorCode")
            nsdManager.stopServiceDiscovery(this)
        }
    }

    private val resolveListener = object : NsdManager.ResolveListener {
        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
            Log.e("NetworkDiscovery", "Resolve failed: Error $errorCode")
        }

        override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
            Log.d("NetworkDiscovery", "Compatible service endpoint resolved")
            val host = serviceInfo.host
            val port = serviceInfo.port
            val url = "http://${host.hostAddress}:$port/"

            val discovered = DiscoveredServer(
                name = serviceInfo.serviceName,
                host = host,
                port = port,
                resolvedUrl = url
            )

            val current = _discoveredServers.value.toMutableList()
            if (current.none { it.name == discovered.name }) {
                current.add(discovered)
                _discoveredServers.value = current
            }
        }
    }

    fun startDiscovery() {
        try {
            if (!_isDiscovering.value) {
                nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discoveryListener)
            }
        } catch (e: Exception) {
            Log.e("NetworkDiscovery", "Error starting discovery", e)
        }
    }

    fun stopDiscovery() {
        try {
            if (_isDiscovering.value) {
                nsdManager.stopServiceDiscovery(discoveryListener)
            }
        } catch (e: Exception) {
            Log.e("NetworkDiscovery", "Error stopping discovery", e)
        }
    }
}
